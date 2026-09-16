"""Read-only corpus auditing and evidence-linked reference preparation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from isc_helwigii.store import canonical

REFERENCE_AXES = ("genre", "language", "period", "archive", "other", "composition_family")
UNKNOWN_VALUES = frozenset(
    {"", "-", "?", "n/a", "none", "null", "und", "unknown", "unidentified", "undetermined"}
)


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_json(value, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _snapshot(store):
    """Load the relevant project state with three bounded queries in one transaction."""
    with store.connection() as con:
        con.execute("BEGIN")
        sources = [
            dict(row)
            for row in con.execute(
                """SELECT id,source,license,checksum,adapter,created_at
                FROM source_snapshots ORDER BY id"""
            )
        ]
        editions = []
        for row in con.execute(
            """SELECT e.id,e.artifact_id,e.snapshot_id,e.record,
            a.source,a.external_id,s.license,s.checksum,s.adapter
            FROM editions e
            JOIN artifacts a ON a.id=e.artifact_id
            JOIN source_snapshots s ON s.id=e.snapshot_id
            ORDER BY e.id"""
        ):
            entry = dict(row)
            entry["record_json"] = entry.pop("record")
            entry["record"] = _parse_json(entry["record_json"], None)
            editions.append(entry)
        annotations = []
        for row in con.execute(
            """SELECT a.id,a.artifact_id,a.kind,a.payload,a.actor,a.origin,a.evidence,
            a.supersedes,a.created_at,r.seq,r.decision,r.actor AS review_actor,
            r.reason,r.created_at AS review_created_at
            FROM annotations a LEFT JOIN review_events r ON r.annotation_id=a.id
            ORDER BY a.id,r.seq"""
        ):
            annotations.append(dict(row))
        con.rollback()

    by_annotation = {}
    for row in annotations:
        annotation = by_annotation.setdefault(
            row["id"],
            {
                "id": row["id"],
                "artifact_id": row["artifact_id"],
                "kind": row["kind"],
                "payload": _parse_json(row["payload"], None),
                "actor": row["actor"],
                "origin": row["origin"],
                "evidence": _parse_json(row["evidence"], None),
                "supersedes": row["supersedes"],
                "created_at": row["created_at"],
                "reviews": [],
            },
        )
        if row["seq"] is not None:
            annotation["reviews"].append(
                {
                    "seq": row["seq"],
                    "decision": row["decision"],
                    "actor": row["review_actor"],
                    "reason": row["reason"],
                    "created_at": row["review_created_at"],
                }
            )
    annotation_rows = [by_annotation[key] for key in sorted(by_annotation)]
    for annotation in annotation_rows:
        annotation["status"] = (
            annotation["reviews"][-1]["decision"] if annotation["reviews"] else "pending"
        )
    superseded = {
        annotation["supersedes"]
        for annotation in annotation_rows
        if annotation["status"] == "accepted" and annotation["supersedes"]
    }
    for annotation in annotation_rows:
        if annotation["id"] in superseded:
            annotation["status"] = "superseded"

    fingerprint_input = {
        "sources": [
            {key: source[key] for key in ("id", "source", "license", "checksum", "adapter")}
            for source in sources
        ],
        "editions": [
            {
                key: edition[key]
                for key in ("id", "artifact_id", "snapshot_id", "source", "external_id")
            }
            | {"record": edition["record"]}
            for edition in editions
        ],
        "annotations": annotation_rows,
    }
    return {
        "sources": sources,
        "editions": editions,
        "annotations": annotation_rows,
        "fingerprint": _sha256(canonical(fingerprint_input)),
    }


def _clean_scalar(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _metadata(record, field):
    if not isinstance(record, dict):
        return None, None, True
    malformed = False
    observed_path = None
    if field in record:
        observed_path = field
        raw = record[field]
        value = _clean_scalar(raw)
        if value is not None and str(value).casefold() not in UNKNOWN_VALUES:
            if field != "language" or isinstance(value, str):
                return value, field, False
            malformed = True
        elif raw is not None and (not isinstance(raw, str) or not raw.strip()):
            malformed = True
    legacy = record.get("legacy_metadata")
    if legacy is not None and not isinstance(legacy, dict):
        return None, observed_path, True
    if isinstance(legacy, dict) and field in legacy:
        observed_path = f"legacy_metadata.{field}"
        raw = legacy[field]
        value = _clean_scalar(raw)
        if value is not None and str(value).casefold() not in UNKNOWN_VALUES:
            if field != "language" or isinstance(value, str):
                return value, observed_path, malformed
            malformed = True
        elif raw is not None and (not isinstance(raw, str) or not raw.strip()):
            malformed = True
    return None, observed_path, malformed


def _normalized_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _readable_text(value):
    normalized = _normalized_text(value)
    if not normalized:
        return False
    stripped = normalized
    for character in "[](){}<>.?…!—–-⸢⸣⌈⌉":
        stripped = stripped.replace(character, " ")
    tokens = stripped.split()
    return bool(tokens) and any(token not in {"x", "xx", "xxx", "lacuna"} for token in tokens)


def _accepted_categories(snapshot):
    result = defaultdict(lambda: defaultdict(list))
    for annotation in snapshot["annotations"]:
        payload = annotation["payload"]
        if (
            annotation["kind"] != "category"
            or annotation["status"] != "accepted"
            or not isinstance(payload, dict)
        ):
            continue
        axis = _clean_scalar(payload.get("axis"))
        label = _clean_scalar(payload.get("label"))
        if not isinstance(axis, str) or not isinstance(label, str):
            continue
        if label.casefold() in UNKNOWN_VALUES:
            continue
        result[annotation["artifact_id"]][axis].append(annotation)
    return result


def _edition_quality(snapshot):
    editions = snapshot["editions"]
    artifact_editions = Counter(row["artifact_id"] for row in editions)
    external_sources = defaultdict(set)
    for row in editions:
        external_sources[row["external_id"]].add(row["source"])

    text_groups = defaultdict(list)
    for row in editions:
        record = row["record"]
        text = record.get("text", "") if isinstance(record, dict) else ""
        normalized = _normalized_text(text)
        if normalized and _readable_text(text):
            text_groups[normalized].append(row["id"])
    duplicate_ids = {
        edition_id for ids in text_groups.values() if len(ids) > 1 for edition_id in ids
    }
    accepted = _accepted_categories(snapshot)
    quality = []
    for edition in editions:
        record = edition["record"]
        language, language_path, language_bad = _metadata(record, "language")
        period, period_path, period_bad = _metadata(record, "period")
        provenience, provenience_path, provenience_bad = _metadata(record, "provenience")
        text = record.get("text", "") if isinstance(record, dict) else ""
        normalized = _normalized_text(text)
        issues = []
        if language is None:
            issues.append("unknown_language")
        if not normalized:
            issues.append("empty_text")
        elif not _readable_text(text):
            issues.append("unreadable_text")
        if period is None:
            issues.append("missing_period")
        if provenience is None:
            issues.append("missing_provenience")
        if not isinstance(record, dict) or language_bad or period_bad or provenience_bad:
            issues.append("malformed_metadata")
        if isinstance(record, dict) and record.get("legacy") is True:
            issues.append("legacy_record")
        if isinstance(record, dict) and record.get("synthetic") is True:
            issues.append("synthetic_record")
        family_labels = {
            annotation["payload"]["label"]
            for annotation in accepted[edition["artifact_id"]].get("composition_family", [])
        }
        if not family_labels:
            issues.append("missing_accepted_composition_family")
        elif len(family_labels) > 1:
            issues.append("conflicting_accepted_composition_family")
        if edition["id"] in duplicate_ids:
            issues.append("exact_normalized_text_duplicate")
        if artifact_editions[edition["artifact_id"]] > 1:
            issues.append("multiple_editions")
        if len(external_sources[edition["external_id"]]) > 1:
            issues.append("cross_source_external_id_collision")
        quality.append(
            {
                "id": edition["id"],
                "edition_id": edition["id"],
                "artifact_id": edition["artifact_id"],
                "snapshot_id": edition["snapshot_id"],
                "source": edition["source"],
                "external_id": edition["external_id"],
                "metadata": {
                    "language": language if language is not None else "[unknown]",
                    "period": period,
                    "provenience": provenience,
                },
                "metadata_paths": {
                    "language": language_path,
                    "period": period_path,
                    "provenience": provenience_path,
                },
                "text_fingerprint": _sha256(normalized) if normalized else None,
                "issues": issues,
            }
        )
    return quality


def audit_corpus(store) -> dict:
    """Return a deterministic, read-only corpus inventory and bounded issue queue."""
    snapshot = _snapshot(store)
    quality = _edition_quality(snapshot)
    issue_counts = Counter(issue for row in quality for issue in row["issues"])
    issue_rows = [row for row in quality if row["issues"]]
    language_counts = Counter(row["metadata"]["language"] for row in quality)
    source_counts = Counter(row["source"] for row in quality)
    snapshot_counts = Counter(row["snapshot_id"] for row in snapshot["editions"])
    sources = [
        {
            **source,
            "edition_count": snapshot_counts[source["id"]],
            "rights_status": "recorded statement; not independently validated",
        }
        for source in snapshot["sources"]
    ]
    return {
        "method": "corpus-audit-v1",
        "fingerprint": snapshot["fingerprint"],
        "counts": {
            "artifacts": len({row["artifact_id"] for row in snapshot["editions"]}),
            "editions": len(snapshot["editions"]),
            "snapshots": len(snapshot["sources"]),
            "issues": sum(issue_counts.values()),
            "issue_rows": len(issue_rows),
        },
        "sources": sources,
        "distributions": {
            "language": dict(sorted(language_counts.items())),
            "source": dict(sorted(source_counts.items())),
            "issues": dict(sorted(issue_counts.items())),
        },
        "editions": issue_rows,
        "limitations": [
            "Metadata completeness does not establish linguistic correctness, historical validity, representativeness or source rights.",
            "Exact text matching uses NFC, casefolding and collapsed whitespace only; diacritics, damage notation and index digits remain distinct.",
            "Empty text and text consisting only of brackets, punctuation, x-markers or 'lacuna' is treated as unreadable and never used as duplicate identity.",
            "The export retains every actionable edition row; the interface filters the full queue and displays bounded pages.",
        ],
    }


class _Components:
    def __init__(self, keys):
        self.parent = {key: key for key in keys}

    def root(self, key):
        parent = self.parent
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(self, left, right):
        left, right = self.root(left), self.root(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def _annotation_evidence(annotation):
    return {
        "annotation_id": annotation["id"],
        "actor": annotation["actor"],
        "origin": annotation["origin"],
        "evidence": annotation["evidence"],
        "supersedes": annotation["supersedes"],
        "reviews": annotation["reviews"],
    }


def _label_groups(accepted, artifact_id, axis):
    annotations = accepted[artifact_id].get(axis, [])
    labels = defaultdict(list)
    for annotation in annotations:
        labels[annotation["payload"]["label"]].append(annotation)
    return labels


def prepare_reference_set(store, *, axis="genre", seed=42) -> dict:
    """Prepare a proposed grouped split from explicit, currently accepted evidence."""
    if axis not in REFERENCE_AXES:
        raise ValueError(f"axis must be one of: {', '.join(REFERENCE_AXES)}")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    snapshot = _snapshot(store)
    editions = snapshot["editions"]
    accepted = _accepted_categories(snapshot)
    components = _Components(row["id"] for row in editions)

    by_artifact = defaultdict(list)
    by_text = defaultdict(list)
    for edition in editions:
        by_artifact[edition["artifact_id"]].append(edition["id"])
        record = edition["record"]
        text = record.get("text", "") if isinstance(record, dict) else ""
        normalized = _normalized_text(text)
        if normalized and _readable_text(text):
            by_text[normalized].append(edition["id"])
    for groups in (by_artifact.values(), by_text.values()):
        for ids in groups:
            for other in ids[1:]:
                components.union(ids[0], other)

    by_family = defaultdict(list)
    for artifact_id, axes in accepted.items():
        edition_ids = by_artifact.get(artifact_id, [])
        for annotation in axes.get("composition_family", []):
            by_family[annotation["payload"]["label"]].extend(edition_ids)
    for ids in by_family.values():
        for other in ids[1:]:
            components.union(ids[0], other)

    items = []
    exclusions = []
    for edition in editions:
        record = edition["record"]
        language, language_path, language_bad = _metadata(record, "language")
        text = record.get("text", "") if isinstance(record, dict) else ""
        labels = _label_groups(accepted, edition["artifact_id"], axis)
        families = _label_groups(accepted, edition["artifact_id"], "composition_family")
        reasons = []
        if len(labels) == 0:
            reasons.append(f"missing_accepted_{axis}")
        elif len(labels) > 1:
            reasons.append(f"conflicting_accepted_{axis}")
        if len(families) == 0:
            reasons.append("missing_accepted_composition_family")
        elif len(families) > 1:
            reasons.append("conflicting_accepted_composition_family")
        if language is None or language_bad:
            reasons.append("unknown_language")
        if not _normalized_text(text):
            reasons.append("empty_text")
        elif not _readable_text(text):
            reasons.append("unreadable_text")
        if not isinstance(record, dict):
            reasons.append("malformed_record")
        elif record.get("synthetic") is True:
            reasons.append("synthetic_record")
        if reasons:
            exclusions.append(
                {
                    "id": edition["id"],
                    "edition_id": edition["id"],
                    "artifact_id": edition["artifact_id"],
                    "snapshot_id": edition["snapshot_id"],
                    "source": edition["source"],
                    "external_id": edition["external_id"],
                    "reasons": list(dict.fromkeys(reasons)),
                }
            )
            continue

        label = next(iter(labels))
        family = next(iter(families))
        label_evidence = [_annotation_evidence(value) for value in labels[label]]
        family_evidence = [_annotation_evidence(value) for value in families[family]]
        items.append(
            {
                "id": edition["id"],
                "edition_id": edition["id"],
                "artifact_id": edition["artifact_id"],
                "snapshot_id": edition["snapshot_id"],
                "source": edition["source"],
                "external_id": edition["external_id"],
                "language": language,
                "language_path": language_path,
                "text": text,
                "source_record_checksum": _sha256(canonical(record)),
                "source_snapshot_checksum": edition["checksum"],
                "source_adapter": edition["adapter"],
                "source_rights": edition["license"],
                "label": label,
                "family": family,
                "accepted_evidence": {
                    "label": label_evidence[0],
                    "family": family_evidence[0],
                    "label_annotations": label_evidence,
                    "family_annotations": family_evidence,
                },
            }
        )

    items.sort(key=lambda row: row["id"])
    exclusions.sort(key=lambda row: row["id"])
    assignments = {}
    for item in items:
        bucket = int(_sha256(f"{seed}:{components.root(item['id'])}"), 16) % 100
        assignments[item["id"]] = "train" if bucket < 80 else "dev" if bucket < 90 else "test"
    split_counts = Counter(assignments.values())
    languages_by_split = defaultdict(Counter)
    for item in items:
        languages_by_split[assignments[item["id"]]][str(item["language"])] += 1
    split_names = ("train", "dev", "test")
    fingerprint = _sha256(
        canonical(
            {
                "corpus_fingerprint": snapshot["fingerprint"],
                "axis": axis,
                "seed": seed,
                "item_ids": [item["id"] for item in items],
            }
        )
    )
    return {
        "method": "accepted-category-reference-v1",
        "fingerprint": fingerprint,
        "corpus_fingerprint": snapshot["fingerprint"],
        "parameters": {"axis": axis, "seed": seed},
        "status": "ready" if items else "abstained",
        "items": items,
        "exclusions": exclusions,
        "assignments": assignments,
        "counts": {
            "artifacts": len({row["artifact_id"] for row in editions}),
            "editions": len(editions),
            "eligible": len(items),
            "excluded": len(exclusions),
            "splits": {name: split_counts[name] for name in split_names},
            "languages_by_split": {
                name: dict(sorted(languages_by_split[name].items())) for name in split_names
            },
        },
        "gold": {item["id"]: item["label"] for item in items},
        "limitations": [
            "This is an evidence-linked proposed split, not a certified gold corpus or representative benchmark.",
            "Accepted local annotations are editorial evidence; actor names are local attribution, not authenticated expert status.",
            "A recorded language is a technical inclusion gate, not independent language verification.",
            "Source-rights statements are carried through but are not interpreted as redistribution clearance.",
            "Exact grouping uses NFC, casefolding and collapsed whitespace only; near duplicates require editorial family annotation.",
            "Assignments can move when the corpus changes; compare corpus and export fingerprints before reuse.",
        ],
    }


def write_json_export(value, destination) -> None:
    """Atomically publish JSON at a new path without overwriting an existing file."""
    destination = Path(destination).expanduser().resolve()
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    if not destination.parent.is_dir():
        raise ValueError("export parent directory does not exist")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise ValueError(f"export destination already exists: {destination}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
