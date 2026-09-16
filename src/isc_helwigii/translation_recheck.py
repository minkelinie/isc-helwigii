"""Append-only, offline quality checks of immutable translation proposals."""

import json

from isc_helwigii.store import canonical, digest, required
from isc_helwigii.translation_quality import assess_translation, render_quality_text

METHOD = "translation-quality-recheck-v1"
INPUT_FORMATS = ("transliteration", "complex-transliteration", "cuneiform")
SOURCE_LANGUAGES = ("sux", "akk")


def _inputs(annotation, edition, source_language, input_format):
    payload = annotation["payload"]
    return {
        "annotation_id": annotation["id"],
        "annotation_payload_sha256": digest(canonical(payload).encode()),
        "artifact_id": edition["artifact_id"],
        "edition_id": edition["id"],
        "snapshot_id": edition["snapshot_id"],
        "start": payload["start"],
        "end": payload["end"],
        "source_text": edition["text"][payload["start"] : payload["end"]],
        "translation_text": payload["text"],
        "declared_language": edition.get("language"),
        "source_language": source_language,
        "target_language": payload["target_language"],
        "input_format": input_format,
    }


def recheck_translation(store, annotation_id, *, actor, source_language, input_format):
    """Screen a saved proposal; never generate, edit or accept a translation.

    Language and notation are explicit research choices, recorded independently
    of source metadata. The source and proposal are immutable, so appending the
    result after the read transaction cannot race with a revision of either.
    """
    required(actor, "actor")
    if source_language not in SOURCE_LANGUAGES:
        raise ValueError("source_language must be sux or akk")
    if input_format not in INPUT_FORMATS:
        raise ValueError("unsupported input_format")
    with store.connection() as con:
        row = con.execute(
            "SELECT * FROM annotations WHERE id=? AND kind='translation'", (annotation_id,)
        ).fetchone()
        if row is None:
            raise ValueError("translation annotation not found")
        annotation = {"id": row["id"], "payload": json.loads(row["payload"])}
        row = con.execute(
            "SELECT * FROM editions WHERE id=? AND artifact_id=?",
            (annotation["payload"]["edition_id"], row["artifact_id"]),
        ).fetchone()
        if row is None:
            raise ValueError("translation source edition not found")
        edition = {
            **json.loads(row["record"]),
            **{key: row[key] for key in ("id", "artifact_id", "snapshot_id")},
        }
    inputs = _inputs(annotation, edition, source_language, input_format)
    report = assess_translation(
        inputs["source_text"],
        inputs["translation_text"],
        source_language=source_language,
        target_language=inputs["target_language"],
        input_format=input_format,
    )
    run_id = store.save_run(METHOD, inputs, report, actor=actor)
    return {"run_id": run_id, "method": METHOD, "inputs": inputs, "outputs": report}


def attach_quality_rechecks(con, annotations, edition):
    """Attach matching evidence within the caller's worksheet read snapshot.

    Generic experiment runs may contain user-supplied data. Only records bound
    to this exact proposal, passage and target belong on its worksheet. This
    verifies the binding, not the scientific correctness of a report.
    """
    by_id = {annotation["id"]: annotation for annotation in annotations}
    for annotation in annotations:
        annotation["quality_rechecks"] = []
    if not annotations:
        return
    for row in con.execute(
        "SELECT * FROM experiment_runs WHERE method=? "
        "AND json_extract(inputs, '$.edition_id')=? ORDER BY rowid",
        (METHOD, edition["id"]),
    ):
        inputs, report = json.loads(row["inputs"]), json.loads(row["outputs"])
        if not isinstance(inputs, dict) or not isinstance(report, dict):
            continue
        if not isinstance(inputs.get("annotation_id"), str):
            continue
        annotation = by_id.get(inputs["annotation_id"])
        language, notation = inputs.get("source_language"), inputs.get("input_format")
        if annotation is None or language not in SOURCE_LANGUAGES or notation not in INPUT_FORMATS:
            continue
        if inputs != _inputs(annotation, edition, language, notation):
            continue
        expected = {
            "source_sha256": digest(inputs["source_text"].encode()),
            "translation_sha256": digest(inputs["translation_text"].encode()),
            "source_language": language,
            "target_language": inputs["target_language"],
            "input_format": notation,
        }
        if any(report.get(key) != value for key, value in expected.items()):
            continue
        # Runs are a generic user-data channel. An incomplete imported report
        # must not break the worksheet; its raw evidence remains in the run log.
        try:
            if any(
                type(report["quantities"][key]) is not int or report["quantities"][key] < 0
                for key in ("checked_count", "missing_count")
            ):
                continue
            render_quality_text(report)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError):
            continue
        annotation["quality_rechecks"].append(
            {
                **{key: row[key] for key in ("id", "method", "actor", "created_at")},
                "inputs": inputs,
                "outputs": report,
            }
        )
