import sqlite3
from contextlib import closing

import pytest

from isc_helwigii.bundles import file_hash
from isc_helwigii.legacy import import_legacy
from isc_helwigii.store import ResearchStore


def test_readonly_legacy_sample_preserves_source_and_untrusted_labels(tmp_path):
    legacy = tmp_path / "legacy.db"
    with closing(sqlite3.connect(legacy)) as con:
        con.execute(
            "CREATE TABLE tablets (id TEXT, transliteration TEXT, language TEXT, myth_labels_json TEXT)"
        )
        con.execute("INSERT INTO tablets VALUES(?,?,?,?)", ("A", "a b", "akk", '["legacy guess"]'))
        con.commit()
    before = file_hash(legacy)
    store = ResearchStore(tmp_path / "research.db")
    store.initialize()
    report = import_legacy(store, legacy, source="legacy-private", license="private", limit=1)
    assert report["record_count"] == 1
    dossier = store.dossier(store.artifacts()[0]["id"])
    assert dossier["editions"][0]["record"]["text"] == "a b"
    assert (
        dossier["editions"][0]["record"]["legacy_metadata"]["myth_labels_json"]
        == '["legacy guess"]'
    )
    assert dossier["annotations"] == []
    assert file_hash(legacy) == before
    with pytest.raises(ValueError):
        import_legacy(store, legacy, source="x", license="private", limit=0)
