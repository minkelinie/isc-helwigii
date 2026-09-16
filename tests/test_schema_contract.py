import json
import sqlite3
import zipfile
from contextlib import closing

import pytest

from isc_helwigii.bundles import export_bundle, file_hash, restore_bundle
from isc_helwigii.database import inspect_database
from isc_helwigii.store import ResearchStore


@pytest.mark.parametrize(
    "removed",
    [
        "PRIMARY KEY",
        "NOT NULL",
        "REFERENCES artifacts(id)",
        ", UNIQUE(source, external_id)",
        "CHECK(decision IN ('accepted','rejected'))",
    ],
)
def test_weakened_constraints_rejected_at_open_health_and_export(tmp_path, removed):
    original = ResearchStore(tmp_path / "original.db")
    original.initialize()
    with original.connection() as con:
        statements = [
            row[0]
            for row in con.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type='trigger'"
            )
        ]
    # Keep names, columns, schema version and all immutable triggers identical.
    sql = ";\n".join(" ".join(s.split()) for s in statements)
    assert removed in sql
    weakened = ResearchStore(tmp_path / "weakened.db")
    with closing(sqlite3.connect(weakened.path)) as con:
        con.executescript(sql.replace(removed, "") + "; PRAGMA user_version=1;")
    with pytest.raises(ValueError, match="schema"):
        weakened.statistics()
    report = inspect_database(weakened.path)
    assert report.status == "degraded"
    assert "schema" in report.error
    with pytest.raises(ValueError, match="schema"):
        export_bundle(weakened, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()
    archive = tmp_path / "forged.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(weakened.path, "project.sqlite3")
        bundle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "isc-research-bundle-v1",
                    "sha256": file_hash(weakened.path),
                }
            ),
        )
    with pytest.raises(ValueError, match="schema"):
        restore_bundle(archive, tmp_path / "restored.db")
    assert not (tmp_path / "restored.db").exists()
