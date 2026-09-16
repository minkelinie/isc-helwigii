"""Rechecks add evidence to an exact saved proposal without revising it."""

import json
import sqlite3
from contextlib import closing, contextmanager

import pytest

from isc_helwigii.cli import main
from isc_helwigii.store import ResearchStore, canonical
from isc_helwigii.translation import build_translation_sheet, render_translation_markdown
from isc_helwigii.translation_recheck import METHOD, recheck_translation


@pytest.fixture
def proposal(tmp_path):
    store = ResearchStore(tmp_path / "recheck.db")
    store.initialize()
    source = "𒀭\n1(disz) udu\n1(disz) udu"
    store.import_records(
        b"synthetic recheck fixture",
        [{"external_id": "SYN-RECHECK", "text": source, "language": "sux", "synthetic": True}],
        source="synthetic",
        license="test only",
    )
    edition = store.dossier(store.artifacts()[0]["id"])["editions"][0]
    start = source.rindex("1(disz)")
    annotation = store.annotate(
        edition["artifact_id"],
        "translation",
        {
            "edition_id": edition["id"],
            "start": start,
            "end": len(source),
            "target_language": "en",
            "text": "one sheep",
        },
        actor="original author",
        evidence=[edition["snapshot_id"], edition["id"]],
    )
    return store, edition, annotation


def recheck(store, annotation, **kwargs):
    return recheck_translation(
        store,
        annotation,
        actor="rechecker",
        source_language="sux",
        input_format="transliteration",
        **kwargs,
    )


@pytest.mark.parametrize("decision", [None, "accepted", "rejected"])
def test_recheck_preserves_sources_proposals_reviews_and_coverage(proposal, decision):
    store, edition, annotation = proposal
    if decision:
        store.review(annotation, decision, actor="reviewer", reason="synthetic review")
    before = store.dossier(edition["artifact_id"])
    sheet_before = build_translation_sheet(store, edition["id"], "en")
    result = recheck(store, annotation)
    assert store.dossier(edition["artifact_id"]) == before
    inputs, report = result["inputs"], result["outputs"]
    assert inputs["annotation_id"] == annotation
    assert inputs["start"] == before["annotations"][0]["payload"]["start"]
    assert inputs["source_text"] == "1(disz) udu"
    assert report["quantities"]["missing_count"] == 0
    assert report["quantities"]["checked_count"] == 1
    assert report["quantities"]["observations"][0]["start"] == 0
    assert report["quantities"]["observations"][0]["target_match"]["text"] == "one"
    sheet = build_translation_sheet(store, edition["id"], "en")
    check = sheet["annotations"][0]["quality_rechecks"][0]
    assert check["id"] == result["run_id"]
    assert check["actor"] == "rechecker"
    assert check["created_at"]
    assert check["outputs"] == report
    assert sheet["coverage"] == sheet_before["coverage"]
    assert sheet["fingerprint"] != sheet_before["fingerprint"]
    assert len(store.runs()) == 1
    markdown = render_translation_markdown(sheet)
    assert "Hercontrole" in markdown
    assert result["run_id"] in markdown
    assert "rechecker" in markdown
    assert report["implementation_sha256"] in markdown
    assert build_translation_sheet(store, edition["id"], "en") == sheet
    assert len(store.runs()) == 1  # Viewing/exporting cannot create another run.


def test_multiple_explicit_checks_remain_ordered_and_scoped(proposal):
    store, edition, annotation = proposal
    first = recheck(store, annotation)
    second = recheck(store, annotation)
    checks = build_translation_sheet(store, edition["id"], "en")["annotations"][0][
        "quality_rechecks"
    ]
    assert [check["id"] for check in checks] == [first["run_id"], second["run_id"]]
    assert build_translation_sheet(store, edition["id"], "nl")["annotations"] == []
    other = store.annotate(
        edition["artifact_id"],
        "translation",
        {"edition_id": edition["id"], "start": 0, "end": 1, "target_language": "en", "text": "god"},
        actor="other",
        evidence=[edition["id"]],
    )
    sheet = build_translation_sheet(store, edition["id"], "en")
    assert next(a for a in sheet["annotations"] if a["id"] == other)["quality_rechecks"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor", " "),
        ("source_language", "unknown"),
        ("input_format", "guess"),
        ("annotation_id", "absent"),
    ],
)
def test_invalid_request_creates_no_run(proposal, field, value):
    store, _, annotation = proposal
    args = {
        "annotation_id": annotation,
        "actor": "rechecker",
        "source_language": "sux",
        "input_format": "transliteration",
    }
    args[field] = value
    with pytest.raises(ValueError):
        recheck_translation(store, **args)
    assert store.runs() == []


def test_mismatched_run_evidence_is_not_attached_to_sheet(proposal):
    store, edition, annotation = proposal
    valid = recheck(store, annotation)
    store.save_run(METHOD, {**valid["inputs"], "start": 0}, valid["outputs"], actor="wrong span")
    store.save_run(
        METHOD,
        valid["inputs"],
        {**valid["outputs"], "translation_sha256": "wrong"},
        actor="wrong output",
    )
    sheet = build_translation_sheet(store, edition["id"], "en")
    assert [r["id"] for r in sheet["annotations"][0]["quality_rechecks"]] == [valid["run_id"]]
    assert len(store.runs()) == 3  # Evidence remains in the experiment log.


def test_incomplete_or_malformed_user_run_does_not_break_export(proposal):
    store, edition, annotation = proposal
    valid = recheck(store, annotation)
    for inputs, outputs in [
        ({**valid["inputs"], "annotation_id": []}, valid["outputs"]),
        (valid["inputs"], {k: v for k, v in valid["outputs"].items() if k != "quantities"}),
        (valid["inputs"], {**valid["outputs"], "limitations": []}),
        (valid["inputs"], {**valid["outputs"], "quantities": {"checked_count": -1}}),
        (valid["inputs"], []),
    ]:
        store.save_run(METHOD, inputs, outputs, actor="imported malformed run")
    sheet = build_translation_sheet(store, edition["id"], "en")
    assert len(sheet["annotations"][0]["quality_rechecks"]) == 1
    assert valid["run_id"] in render_translation_markdown(sheet)
    assert len(store.runs()) == 6


def test_rechecks_survive_project_export_restore(proposal, tmp_path):
    from isc_helwigii.bundles import export_bundle, restore_bundle

    store, edition, annotation = proposal
    recheck(store, annotation)
    before = build_translation_sheet(store, edition["id"], "en")
    bundle = tmp_path / "checked.zip"
    export_bundle(store, bundle)
    restored = restore_bundle(bundle, tmp_path / "restored.db")
    assert build_translation_sheet(restored, edition["id"], "en") == before


def test_recheck_and_reviews_share_one_export_snapshot(proposal, monkeypatch):
    store, edition, annotation = proposal
    run = recheck(store, annotation)
    with closing(sqlite3.connect(store.path)) as con:
        con.execute("PRAGMA journal_mode=WAL")
    connection = store.connection
    inserted = False

    @contextmanager
    def concurrent_connection(**kwargs):
        nonlocal inserted
        with connection(**kwargs) as con:

            def insert_after_snapshot(statement):
                nonlocal inserted
                if "FROM experiment_runs" in statement and not inserted:
                    inserted = True
                    with closing(sqlite3.connect(store.path)) as writer:
                        writer.execute(
                            "INSERT INTO experiment_runs VALUES(?,?,?,?,?,?)",
                            (
                                "concurrent",
                                METHOD,
                                canonical(run["inputs"]),
                                canonical(run["outputs"]),
                                "concurrent",
                                "2026-09-15",
                            ),
                        )
                        writer.commit()

            con.set_trace_callback(insert_after_snapshot)
            yield con

    monkeypatch.setattr(store, "connection", concurrent_connection)
    sheet = build_translation_sheet(store, edition["id"], "en")
    assert inserted
    assert len(sheet["annotations"][0]["quality_rechecks"]) == 1
    assert (
        len(
            build_translation_sheet(store, edition["id"], "en")["annotations"][0][
                "quality_rechecks"
            ]
        )
        == 2
    )


def test_cli_works_without_inference_and_exports_persistent_history(proposal, capsys):
    store, edition, annotation = proposal
    assert (
        main(
            [
                "recheck-translation",
                str(store.path),
                annotation,
                "--actor",
                "CLI researcher",
                "--source-language",
                "sux",
                "--input-format",
                "transliteration",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    reopened = ResearchStore(store.path)
    assert reopened.runs()[0]["id"] == result["run_id"]
    assert (
        main(["translation-sheet", str(store.path), edition["id"], "--target-language", "en"]) == 0
    )
    sheet = json.loads(capsys.readouterr().out)
    assert sheet["annotations"][0]["quality_rechecks"][0]["actor"] == "CLI researcher"
