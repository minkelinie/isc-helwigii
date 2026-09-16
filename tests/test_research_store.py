import sqlite3
from contextlib import closing

import pytest

from isc_helwigii.store import ResearchStore


@pytest.fixture
def store(tmp_path):
    project = ResearchStore(tmp_path / "research.db")
    project.initialize()
    return project


def imported(store):
    snapshot = store.import_records(
        b"original",
        [{"external_id": "P1", "text": "a b", "language": "akk"}],
        source="test",
        license="private",
    )
    return store.artifacts()[0]["id"], snapshot


def test_import_is_idempotent_and_conflicts_are_preserved(store):
    artifact, snapshot = imported(store)
    assert imported(store) == (artifact, snapshot)
    store.import_records(
        b"corrected",
        [{"external_id": "P1", "text": "a c", "language": "akk"}],
        source="test",
        license="private",
    )
    assert len(store.artifacts()) == 1
    dossier = store.dossier(artifact)
    assert {e["record"]["text"] for e in dossier["editions"]} == {"a b", "a c"}
    assert store.source_bytes(snapshot) == b"original"


def test_evidence_cannot_be_mutated_even_directly(store):
    imported(store)
    with (
        closing(sqlite3.connect(store.path)) as con,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        con.execute("DELETE FROM source_snapshots")


def test_bad_import_rolls_back_everything(store):
    with pytest.raises(ValueError):
        store.import_records(
            b"raw", [{"external_id": "a"}, {"text": "missing ID"}], source="x", license="private"
        )
    assert store.artifacts() == []


def test_unknown_database_is_refused(tmp_path):
    path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(path)) as con:
        con.execute("CREATE TABLE tablets (id TEXT)")
    with pytest.raises(ValueError, match="unrelated"):
        ResearchStore(path).initialize()
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0


def test_review_revision_and_passage_provenance(store):
    artifact, snapshot = imported(store)
    edition = store.dossier(artifact)["editions"][0]["id"]
    annotation = store.annotate(
        artifact,
        "translation",
        {"text": "A B", "target_language": "en", "edition_id": edition, "start": 0, "end": 3},
        actor="researcher",
        evidence=[snapshot],
    )
    assert store.dossier(artifact)["annotations"][0]["status"] == "pending"
    store.review(annotation, "accepted", actor="reviewer", reason="checked source")
    assert store.dossier(artifact)["annotations"][0]["status"] == "accepted"
    revision = store.annotate(
        artifact,
        "translation",
        {"text": "A C", "target_language": "en", "edition_id": edition, "start": 0, "end": 3},
        actor="researcher",
        evidence=[snapshot],
        supersedes=annotation,
    )
    assert store.dossier(artifact)["annotations"][0]["status"] == "accepted"
    store.review(revision, "accepted", actor="reviewer", reason="corrected reading")
    assert store.dossier(artifact)["annotations"][0]["status"] == "superseded"
    with pytest.raises(ValueError):
        store.annotate(
            artifact,
            "motif",
            {"name": "flood", "edition_id": edition, "start": 5, "end": 10},
            actor="a",
            evidence=[snapshot],
        )


def test_annotations_require_real_evidence_and_actor(store):
    artifact, _ = imported(store)
    with pytest.raises(ValueError):
        store.annotate(artifact, "category", {"label": "letter"}, actor="", evidence=["fake"])
    with pytest.raises(ValueError):
        store.annotate(artifact, "category", {"label": "letter"}, actor="a", evidence=["fake"])


def test_assets_and_runs_are_preserved(store):
    artifact, snapshot = imported(store)
    asset = store.add_asset(
        artifact,
        b"image-data",
        name="tablet.png",
        media_type="image/png",
        license="private",
        actor="a",
    )
    assert store.asset_bytes(asset) == b"image-data"
    run = store.save_run(
        "text-jaccard-v1", {"snapshot_ids": [snapshot]}, {"score": 0.25}, actor="a"
    )
    assert store.runs()[0]["id"] == run
    assert store.runs()[0]["outputs"]["score"] == 0.25


def test_missing_project_read_does_not_create_file(tmp_path):
    project = ResearchStore(tmp_path / "absent.db")
    with pytest.raises(ValueError):
        project.artifacts()
    assert not project.path.exists()
