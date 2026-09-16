"""Corpus-wide lexical retrieval with bounded ranking memory and frozen scope."""

import hashlib
import heapq
import json
from pathlib import Path

from isc_helwigii import __version__, analysis
from isc_helwigii.store import canonical, digest, required


def collect_translations(con, query, limit):
    """Stream current accepted translations inside the caller's read snapshot."""
    memory = analysis.translation_memory(
        query["text"], [], query["language"], query["target_language"]
    )
    count = 0
    rows = con.execute("""
        SELECT a.id,a.artifact_id,a.payload,a.evidence,a.actor,
               e.id edition_id,e.record,e.snapshot_id,
               r.seq,r.decision,r.actor reviewer,r.reason,r.created_at
        FROM annotations a
        JOIN editions e ON e.artifact_id=a.artifact_id
        JOIN review_events r ON r.seq=(SELECT MAX(seq) FROM review_events WHERE annotation_id=a.id)
        WHERE a.kind='translation' AND r.decision='accepted'
        AND NOT EXISTS (
            SELECT 1 FROM annotations child
            JOIN review_events cr ON cr.seq=(SELECT MAX(seq) FROM review_events WHERE annotation_id=child.id)
            WHERE child.supersedes=a.id AND cr.decision='accepted'
        ) ORDER BY a.id,e.id
    """)
    for row in rows:
        payload = json.loads(row["payload"])
        if payload["edition_id"] != row["edition_id"]:
            continue
        record = json.loads(row["record"])
        entry = {
            **payload,
            "id": row["id"],
            "artifact_id": row["artifact_id"],
            "snapshot_id": row["snapshot_id"],
            "status": "accepted",
            "language": record.get("language", "unknown"),
            "source_text": record.get("text", "")[payload["start"] : payload["end"]],
            "evidence": json.loads(row["evidence"]),
            "actor": row["actor"],
            "review": {
                "seq": row["seq"],
                "decision": row["decision"],
                "actor": row["reviewer"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            },
        }
        if analysis.translation_memory(
            query["text"], [entry], query["language"], query["target_language"]
        )["candidates"]:
            count += 1
            if len(memory["candidates"]) < limit:
                memory["candidates"].append(entry)
    memory.update(matched_count=count, truncated=count > limit)
    if count:
        memory["status"] = "attested-parallel"
    return memory


def prepare_dossier(store, parameters, *, actor):
    from isc_helwigii import research

    required(actor, "actor")
    edition = store.edition(parameters.get("edition_id"))
    text = edition.get("text", "")
    start, end = parameters.get("start", 0), parameters.get("end", len(text))
    limit = parameters.get("limit", 10)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start <= end <= len(text)
        or (start == end and text)
    ):
        raise ValueError("select a non-empty passage within the source edition")
    target = required(parameters.get("target_language", "nl"), "target_language")
    query = {
        "edition_id": edition["id"],
        "artifact_id": edition["artifact_id"],
        "start": start,
        "end": end,
        "text": text[start:end],
        "language": edition.get("language", "unknown"),
        "target_language": target,
    }
    readable = set(analysis.tokens(query["text"]))
    searchable = bool(readable) and analysis.valid_language(query["language"])
    scope = {"snapshot_ids": [], "edition_count": 0, "eligible_editions": 0}
    manifest = hashlib.sha256()

    with store.connection() as con:
        con.execute("BEGIN")
        scope["snapshot_ids"] = [
            r[0] for r in con.execute("SELECT id FROM source_snapshots ORDER BY id")
        ]

        def candidates():
            for row in con.execute(
                "SELECT e.id,e.artifact_id,e.snapshot_id,e.record,a.source,a.external_id "
                "FROM editions e JOIN artifacts a ON a.id=e.artifact_id ORDER BY e.id"
            ):
                scope["edition_count"] += 1
                manifest.update(canonical([row["id"], digest(row["record"].encode())]).encode())
                record = json.loads(row["record"])
                if (
                    not searchable
                    or row["artifact_id"] == edition["artifact_id"]
                    or record.get("language") != query["language"]
                ):
                    continue
                words = set(analysis.tokens(record.get("text", "")))
                if not words:
                    continue
                scope["eligible_editions"] += 1
                shared = readable & words
                if not shared:
                    continue
                score = len(shared) / len(readable | words)
                yield {
                    "id": row["id"],
                    "artifact_id": row["artifact_id"],
                    "snapshot_id": row["snapshot_id"],
                    "source": row["source"],
                    "external_id": row["external_id"],
                    "text": record.get("text", ""),
                    "language": record.get("language"),
                    "jaccard": score,
                    "title": record.get("title", row["external_id"]),
                    "synthetic": bool(record.get("synthetic")),
                }

        # Only align the retained results; never load 37,000 dossiers or raw sources.
        matches = heapq.nsmallest(limit, candidates(), key=lambda r: (-r["jaccard"], r["id"]))
        scope["last_review_seq"] = con.execute(
            "SELECT COALESCE(MAX(seq),0) FROM review_events"
        ).fetchone()[0]
        memory = (
            collect_translations(con, query, limit)
            if searchable
            else analysis.translation_memory(query["text"], [], query["language"], target)
        )
    scope["manifest_sha256"] = manifest.hexdigest()
    for match in matches:
        match.update(analysis.text_similarity(query["text"], match["text"]))
        match["query_only_tokens"] = sorted(readable - set(match["right_tokens"]))
        match["candidate_only_tokens"] = sorted(set(match["right_tokens"]) - readable)

    outputs = {
        "method": "corpus-lexical-dossier-v1",
        "status": "exploratory" if searchable else "abstained",
        "query": query,
        "corpus": scope,
        "parallels": matches,
        "translation_memory": memory,
        "ranking": "NFC casefold token Jaccard against full editions; ties by edition ID",
        "limitations": [
            "Lexical similarity is not a translation, a physical join or evidence of common ancestry.",
            "Full-edition ranking can miss short parallels inside long texts; no semantic or lemmatic model.",
            "Language labels are imported metadata; different labels are not automatically equated.",
            "Results describe the saved source and review state; rerun after new evidence or reviews.",
        ],
    }
    if not searchable:
        outputs["reason"] = "language unknown or no readable tokens in the selected passage"
    elif not matches:
        outputs["reason"] = "no shared readable tokens in other same-language artifacts"
    inputs = {
        "parameters": {
            **parameters,
            "start": start,
            "end": end,
            "limit": limit,
            "target_language": target,
        },
        "software_version": __version__,
        "edition": edition,
        "corpus": scope,
        "translation_entries": memory["candidates"],
    }
    sources = []
    for path in (Path(__file__), Path(analysis.__file__), Path(research.__file__)):
        source = path.read_text(encoding="utf-8")
        sources.append({"filename": path.name, "source": source, "sha256": digest(source.encode())})
    inputs["implementation"] = sources[0]
    inputs["implementation_dependencies"] = sources[1:]
    run_id = store.save_run(outputs["method"], inputs, outputs, actor=actor)
    return {"run_id": run_id, "outputs": outputs}
