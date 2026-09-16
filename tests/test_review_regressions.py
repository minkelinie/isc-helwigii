import sqlite3
from contextlib import closing

import pytest

from isc_helwigii.analysis import rank_parallels, translation_memory
from isc_helwigii.bundles import export_bundle
from isc_helwigii.store import ResearchStore


@pytest.fixture
def store(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    store.initialize()
    store.import_records(
        b"original",
        [{"external_id": "a", "text": "a b", "language": "akk"}],
        source="x",
        license="private",
    )
    return store


def test_replace_cannot_overwrite_raw_evidence(store):
    with store.connection(write=True) as con:
        row = dict(con.execute("SELECT * FROM source_snapshots").fetchone())
        row["raw"] = b"tampered"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute(
                "INSERT OR REPLACE INTO source_snapshots VALUES(?,?,?,?,?,?,?)", tuple(row.values())
            )
    assert store.source_bytes(row["id"]) == b"original"


def test_revision_cannot_change_translation_scope(store):
    artifact = store.artifacts()[0]["id"]
    edition = store.dossier(artifact)["editions"][0]
    payload = {
        "text": "A",
        "target_language": "en",
        "edition_id": edition["id"],
        "start": 0,
        "end": 1,
    }
    parent = store.annotate(
        artifact, "translation", payload, actor="a", evidence=[edition["snapshot_id"]]
    )
    for change in ({"start": 2, "end": 3}, {"target_language": "nl"}):
        with pytest.raises(ValueError, match="scope"):
            store.annotate(
                artifact,
                "translation",
                {**payload, **change},
                actor="a",
                evidence=[edition["snapshot_id"]],
                supersedes=parent,
            )


def test_missing_integrity_trigger_is_detected(store):
    with closing(sqlite3.connect(store.path)) as con:
        con.execute("DROP TRIGGER immutable_source_snapshots_UPDATE")
    with pytest.raises(ValueError, match="schema"):
        store.artifacts()


def test_export_rejects_inconsistent_source_checksum(store, tmp_path):
    with closing(sqlite3.connect(store.path)) as con:
        trigger = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='immutable_source_snapshots_UPDATE'"
        ).fetchone()[0]
        con.execute("DROP TRIGGER immutable_source_snapshots_UPDATE")
        con.execute("UPDATE source_snapshots SET raw=?", (b"corrupted",))
        con.execute(trigger)
        con.commit()
    with pytest.raises(ValueError, match="checksum"):
        export_bundle(store, tmp_path / "bundle.zip")
    assert not (tmp_path / "bundle.zip").exists()


@pytest.mark.parametrize("language", [None, "", " ", "unknown"])
def test_missing_language_always_abstains(language):
    entries = [
        {
            "source_text": "a",
            "text": "A",
            "language": language,
            "target_language": "en",
            "status": "accepted",
            "evidence": ["x"],
        }
    ]
    assert translation_memory("a", entries, language, "en")["status"] == "abstained"
    assert rank_parallels("a", [{"id": "a", "text": "a", "language": language}], language) == []
