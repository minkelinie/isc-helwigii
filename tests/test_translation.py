import json
import sqlite3
from contextlib import closing, contextmanager

import pytest

from isc_helwigii import translation
from isc_helwigii.cli import main
from isc_helwigii.store import ResearchStore


@pytest.fixture
def project(tmp_path):
    store = ResearchStore(tmp_path / "translation.db")
    store.initialize()
    store.import_records(
        b"synthetic fixture",
        [{"external_id": "SYN-A", "text": "a₂ b\na₂ b\n𒀭 x", "language": "sux", "synthetic": True}],
        source="synthetic",
        license="test only",
    )
    edition = store.dossier(store.artifacts()[0]["id"])["editions"][0]
    return store, edition


def propose(store, edition, start, end, text="Vertaling", target="nl", supersedes=None):
    return store.annotate(
        edition["artifact_id"],
        "translation",
        {
            "edition_id": edition["id"],
            "start": start,
            "end": end,
            "text": text,
            "target_language": target,
            "reference": "Synthetische testreferentie",
        },
        actor="author",
        evidence=[edition["id"], edition["snapshot_id"]],
        supersedes=supersedes,
    )


def accept(store, annotation):
    store.review(annotation, "accepted", actor="reviewer", reason="fixture only")


def test_sheet_anchors_repeated_unicode_passages_and_reports_gaps(project):
    store, edition = project
    first = propose(store, edition, 5, 9, "Tweede voorkomen")
    pending = translation.build_translation_sheet(store, edition["id"])
    assert pending["coverage"]["translated_characters"] == 0
    assert pending["annotations"][0]["status"] == "pending"
    accept(store, first)
    before = store.path.read_bytes()
    sheet = translation.build_translation_sheet(store, edition["id"])
    assert sheet == translation.build_translation_sheet(store, edition["id"])
    assert store.path.read_bytes() == before
    assert sheet["edition"]["license"] == "test only"
    assert sheet["edition"]["synthetic"] is True
    assert [(s["start"], s["end"], s["status"]) for s in sheet["segments"]] == [
        (0, 5, "untranslated"),
        (5, 9, "translated"),
        (9, 13, "untranslated"),
    ]
    assert "".join(s["source_text"] for s in sheet["segments"]) == edition["record"]["text"]
    assert sheet["segments"][1]["candidates"][0]["payload"]["text"] == "Tweede voorkomen"
    assert sheet["coverage"] == {
        "total_characters": 8,
        "translated_characters": 3,
        "conflict_characters": 0,
        "untranslated_characters": 5,
        "ratio": 3 / 8,
    }
    assert sheet["annotations"][0]["review"]["actor"] == "reviewer"
    assert sheet["last_review_seq"] == 1
    assert sheet["fingerprint"] != pending["fingerprint"]


def test_transitive_overlap_never_splits_or_silently_chooses_translations(project):
    store, edition = project
    for start, end in [(0, 4), (3, 7), (6, 9), (10, 13)]:
        accept(store, propose(store, edition, start, end, f"{start}-{end}"))
    sheet = translation.build_translation_sheet(store, edition["id"])
    assert [(s["start"], s["end"], s["status"]) for s in sheet["segments"]] == [
        (0, 9, "conflict"),
        (9, 10, "untranslated"),
        (10, 13, "translated"),
    ]
    assert len(sheet["segments"][0]["candidates"]) == 3
    assert sheet["coverage"]["conflict_characters"] == 6
    assert sheet["coverage"]["translated_characters"] == 2
    assert sheet["coverage"]["ratio"] == 0.25


def test_revisions_rejections_languages_and_editions_keep_distinct_scope(project):
    store, edition = project
    original = propose(store, edition, 0, 4, "Oud")
    accept(store, original)
    revision = propose(store, edition, 0, 4, "Nieuw", supersedes=original)
    accept(store, propose(store, edition, 0, 4, "English", target="en"))
    store.import_records(
        b"second edition",
        [{"external_id": "SYN-A", "text": "a₂ b", "language": "sux"}],
        source="synthetic",
        license="test only",
    )
    second = store.dossier(edition["artifact_id"])["editions"][1]
    accept(store, propose(store, second, 0, 4, "Andere editie"))
    sheet = translation.build_translation_sheet(store, edition["id"])
    assert [a["id"] for a in sheet["segments"][0]["candidates"]] == [original]
    accept(store, revision)
    revised = translation.build_translation_sheet(store, edition["id"])
    assert [a["id"] for a in revised["segments"][0]["candidates"]] == [revision]
    assert {a["id"]: a["status"] for a in revised["annotations"]} == {
        original: "superseded",
        revision: "accepted",
    }
    store.review(revision, "rejected", actor="reviewer", reason="withdrawn")
    restored = translation.build_translation_sheet(store, edition["id"])
    assert restored["segments"][0]["candidates"][0]["id"] == original
    assert len(restored["annotations"]) == 2


def test_touching_spans_are_not_conflicting_and_empty_text_has_no_coverage(project):
    store, edition = project
    for start, end in [(0, 2), (2, 13)]:
        accept(store, propose(store, edition, start, end))
    sheet = translation.build_translation_sheet(store, edition["id"])
    assert sheet["coverage"]["ratio"] == 1
    assert all(s["status"] == "translated" for s in sheet["segments"])
    store.import_records(
        b"empty",
        [{"external_id": "EMPTY", "text": "", "language": "sux"}],
        source="synthetic",
        license="test",
    )
    empty = store.dossier(store.artifacts("EMPTY")[0]["id"])["editions"][0]
    result = translation.build_translation_sheet(store, empty["id"])
    assert result["segments"] == []
    assert result["coverage"]["ratio"] is None
    with pytest.raises(ValueError, match="edition"):
        translation.build_translation_sheet(store, "missing")
    with pytest.raises(ValueError, match="target_language"):
        translation.build_translation_sheet(store, edition["id"], "")


def test_sheet_review_and_annotation_scope_share_a_read_snapshot(project, monkeypatch):
    store, edition = project
    annotation = propose(store, edition, 0, 4)
    with closing(sqlite3.connect(store.path)) as con:
        con.execute("PRAGMA journal_mode=WAL")
    original_connection = store.connection
    committed = False

    @contextmanager
    def concurrent_connection(**kwargs):
        nonlocal committed
        with original_connection(**kwargs) as con:

            def concurrent_review(statement):
                nonlocal committed
                if "FROM annotations" in statement and not committed:
                    committed = True
                    with closing(sqlite3.connect(store.path)) as writer:
                        writer.execute(
                            "INSERT INTO review_events(annotation_id,decision,actor,reason,created_at) VALUES(?,?,?,?,?)",
                            (annotation, "accepted", "concurrent", "fixture", "2026-09-10"),
                        )
                        writer.commit()

            con.set_trace_callback(concurrent_review)
            yield con

    monkeypatch.setattr(store, "connection", concurrent_connection)
    sheet = translation.build_translation_sheet(store, edition["id"])
    assert committed
    assert sheet["last_review_seq"] == 0
    assert sheet["annotations"][0]["status"] == "pending"
    assert sheet["coverage"]["translated_characters"] == 0
    assert translation.build_translation_sheet(store, edition["id"])["coverage"]["ratio"] > 0


def test_readable_export_preserves_provenance_and_marks_conflicts_and_gaps(project):
    store, edition = project
    first = propose(store, edition, 0, 4, "Voorstel\n```\n# Letterlijke tekst")
    accept(store, first)
    accept(store, propose(store, edition, 0, 4, "Alternatief"))
    report = translation.render_translation_markdown(
        translation.build_translation_sheet(store, edition["id"])
    )
    for value in [
        "SYN-A",
        "CONFLICT",
        "NIET VERTAALD",
        "Synthetisch",
        "reviewer",
        "fixture only",
        "test only",
        "Synthetische testreferentie",
        first,
        "Voorstel\n```\n# Letterlijke tekst",
    ]:
        assert value in report
    assert "\n````text\nVoorstel" in report


def test_cli_exports_sheet_and_refuses_overwriting_project_or_existing_file(
    project, tmp_path, capsys
):
    store, edition = project
    destination = tmp_path / "translation.md"
    args = [
        "translation-sheet",
        str(store.path),
        edition["id"],
        "--format",
        "markdown",
        "--output",
        str(destination),
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["edition"]["id"] == edition["id"]
    assert "NIET VERTAALD" in destination.read_text()
    assert main(args) == 2
    assert "exist" in capsys.readouterr().err
    before = store.path.read_bytes()
    assert main(args[:-1] + [str(store.path)]) == 2
    capsys.readouterr()
    assert store.path.read_bytes() == before
    assert main(["translation-sheet", str(store.path), edition["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["coverage"]["ratio"] == 0
    assert main(["translation-sheet", str(store.path), edition["id"], "--format", "markdown"]) == 0
    assert capsys.readouterr().out.startswith("# Vertaalwerkblad")
