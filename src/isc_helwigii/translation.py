"""Read-only translation worksheets anchored to one immutable source edition."""

import json
import re

from isc_helwigii.store import canonical, digest, required


def build_translation_sheet(store, edition_id, target_language="nl"):
    """Keep complete translation spans, conflicts and missing text explicit."""
    required(target_language, "target_language")
    with store.connection() as con:
        con.execute("BEGIN")
        row = con.execute(
            "SELECT e.*,a.source,a.external_id,s.license,s.checksum "
            "FROM editions e JOIN artifacts a ON a.id=e.artifact_id "
            "JOIN source_snapshots s ON s.id=e.snapshot_id WHERE e.id=?",
            (edition_id,),
        ).fetchone()
        if row is None:
            raise ValueError("edition not found")
        edition = {
            **json.loads(row["record"]),
            **{
                k: row[k]
                for k in (
                    "id",
                    "artifact_id",
                    "snapshot_id",
                    "source",
                    "external_id",
                    "license",
                    "checksum",
                )
            },
        }
        last_review_seq = con.execute("SELECT COALESCE(MAX(seq),0) FROM review_events").fetchone()[
            0
        ]
        annotations = []
        for row in con.execute(
            """SELECT a.*,r.seq review_seq,r.decision,r.actor reviewer,r.reason,
                      r.created_at reviewed_at
               FROM annotations a
               LEFT JOIN review_events r ON r.seq=(
                   SELECT MAX(seq) FROM review_events WHERE annotation_id=a.id)
               WHERE a.artifact_id=? AND a.kind='translation' ORDER BY a.rowid""",
            (edition["artifact_id"],),
        ):
            payload = json.loads(row["payload"])
            if payload["edition_id"] != edition_id or payload["target_language"] != target_language:
                continue
            review = None
            if row["review_seq"] is not None:
                review = {
                    "seq": row["review_seq"],
                    "decision": row["decision"],
                    "actor": row["reviewer"],
                    "reason": row["reason"],
                    "created_at": row["reviewed_at"],
                }
            annotations.append(
                {
                    **{
                        k: row[k]
                        for k in ("id", "kind", "actor", "origin", "supersedes", "created_at")
                    },
                    "payload": payload,
                    "evidence": json.loads(row["evidence"]),
                    "status": row["decision"] or "pending",
                    "review": review,
                }
            )
    superseded = {a["supersedes"] for a in annotations if a["status"] == "accepted"}
    for annotation in annotations:
        if annotation["id"] in superseded:
            annotation["status"] = "superseded"
    text = edition.get("text", "")
    accepted = sorted(
        (a for a in annotations if a["status"] == "accepted"),
        key=lambda a: (a["payload"]["start"], a["payload"]["end"], a["id"]),
    )
    # Connected overlapping spans are a single conflict. Translation strings must
    # never be divided by source offsets, or repeated for each overlap boundary.
    groups = []
    for annotation in accepted:
        start, end = annotation["payload"]["start"], annotation["payload"]["end"]
        if groups and start < groups[-1]["end"]:
            groups[-1]["end"] = max(groups[-1]["end"], end)
            groups[-1]["candidates"].append(annotation)
        else:
            groups.append({"start": start, "end": end, "candidates": [annotation]})
    segments = []
    cursor = 0
    for group in groups:
        if cursor < group["start"]:
            segments.append(
                {"start": cursor, "end": group["start"], "status": "untranslated", "candidates": []}
            )
        segments.append(
            {
                **group,
                "status": "translated" if len(group["candidates"]) == 1 else "conflict",
            }
        )
        cursor = group["end"]
    if cursor < len(text):
        segments.append(
            {"start": cursor, "end": len(text), "status": "untranslated", "candidates": []}
        )
    counts = {"translated": 0, "conflict": 0, "untranslated": 0}
    for segment in segments:
        segment["source_text"] = text[segment["start"] : segment["end"]]
        counts[segment["status"]] += sum(not c.isspace() for c in segment["source_text"])
    total = sum(counts.values())
    sheet = {
        "method": "edition-translation-sheet-v1",
        "edition": edition,
        "target_language": target_language,
        "annotations": annotations,
        "segments": segments,
        "coverage": {
            "total_characters": total,
            **{k + "_characters": v for k, v in counts.items()},
            "ratio": counts["translated"] / total if total else None,
        },
        "last_review_seq": last_review_seq,
    }
    sheet["fingerprint"] = digest(canonical(sheet).encode())
    return sheet


def _literal(value):
    """Fence source and editorial text safely, including literal Markdown."""
    value = str(value)
    longest = max((len(m[0]) for m in re.finditer(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{value}\n{fence}"


def render_translation_markdown(sheet):
    """A readable snapshot, with no synthesized or silently resolved translation."""
    edition = sheet["edition"]
    coverage = sheet["coverage"]
    ratio = coverage["ratio"]
    parts = [
        "# Vertaalwerkblad — I.S.C. Helwigii",
        _literal(
            f"Tablet: {edition['external_id']}\nBron: {edition['source']}\n"
            f"Broneditie: {edition['id']}\nMomentopname: {edition['snapshot_id']}\n"
            f"Bronchecksum: {edition['checksum']}\nLicentie: {edition['license']}\n"
            f"Brontaal: {edition.get('language', 'unknown')}\nDoeltaal: {sheet['target_language']}"
        ),
    ]
    if edition.get("synthetic"):
        parts.append("**Synthetisch demonstratierecord; geen historische vertaling.**")
    percentage = f"{ratio:.1%}" if ratio is not None else "niet van toepassing"
    parts.extend(
        [
            f"Redactioneel gedekt: **{percentage}** "
            f"({coverage['translated_characters']}/{coverage['total_characters']} tekens zonder witruimte). "
            "Dit is geen nauwkeurigheidsscore. Alleen geaccepteerde, niet-overlappende vertalingen tellen mee.",
            "Geen automatisch vertaalmodel gebruikt. Ontbrekende tekst blijft open; "
            "overlappende geaccepteerde voorstellen vragen een expliciet redactioneel besluit.",
        ]
    )
    if not sheet["segments"]:
        parts.append("Deze editie bevat geen brontekst.")
    labels = {
        "translated": "BEOORDEELDE VERTALING",
        "conflict": "CONFLICT",
        "untranslated": "NIET VERTAALD",
    }
    for segment in sheet["segments"]:
        if not segment["source_text"].strip() and not segment["candidates"]:
            continue
        parts.extend(
            [
                f"## {labels[segment['status']]} · {segment['start']}–{segment['end']}",
                "Bronpassage:",
                _literal(segment["source_text"]),
            ]
        )
        for annotation in segment["candidates"]:
            payload = annotation["payload"]
            review = annotation["review"]
            parts.extend(
                [
                    f"Voorstel voor bronposities {payload['start']}–{payload['end']}:",
                    _literal(payload["text"]),
                    _literal(
                        f"Annotatie: {annotation['id']}\nAuteur: {annotation['actor']}\n"
                        f"Herkomst: {annotation['origin']}\n"
                        f"Referentie: {payload.get('reference') or 'niet opgegeven'}\n"
                        f"Bewijs: {', '.join(annotation['evidence'])}\n"
                        f"Beoordelaar: {review['actor']}\nBesluit: {review['decision']}\n"
                        f"Grond: {review['reason']}\n"
                        f"Beoordeling: {review['seq']} · {review['created_at']}"
                    ),
                ]
            )
    inactive = [a for a in sheet["annotations"] if a["status"] != "accepted"]
    if inactive:
        parts.append("## Overige voorstellen — niet opgenomen in de vertaling")
        for annotation in inactive:
            payload = annotation["payload"]
            parts.append(
                _literal(
                    f"Annotatie: {annotation['id']}\nStatus: {annotation['status']}\n"
                    f"Bronposities: {payload['start']}–{payload['end']}\n"
                    f"Auteur: {annotation['actor']}\nVertaling: {payload['text']}\n"
                    f"Referentie: {payload.get('reference') or 'niet opgegeven'}"
                )
            )
    parts.extend(
        [
            "## Momentopname",
            _literal(
                f"Methode: {sheet['method']}\nLaatste projectbeoordeling: {sheet['last_review_seq']}\n"
                f"SHA-256 werkblad: {sheet['fingerprint']}"
            ),
            "Voor de volledige vastgelegde invoer en annotatiegegevens: bewaar ook de JSON-export. "
            "Bereid opnieuw voor na nieuwe voorstellen of beoordelingen.",
        ]
    )
    return "\n\n".join(parts) + "\n"
