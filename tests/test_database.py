import sqlite3
from contextlib import closing
from pathlib import Path

from isc_helwigii.database import inspect_database
from isc_helwigii.store import ResearchStore


def test_missing_database_is_unavailable_without_creating_it(tmp_path: Path) -> None:
    """Catches a health check that creates an empty database as a side effect."""
    path = tmp_path / "missing.db"

    report = inspect_database(path)

    assert report.status == "unavailable"
    assert report.error == "database does not exist"
    assert not path.exists()


def test_empty_database_is_unknown(tmp_path: Path) -> None:
    """Catches an arbitrary SQLite file being reported as a valid research store."""
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()

    report = inspect_database(path)

    assert report.status == "degraded"
    assert report.schema == "unknown"
    assert report.tables == ()


def test_legacy_database_counts_known_tables(tmp_path: Path) -> None:
    """Catches legacy data becoming invisible to the foundation health contract."""
    path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE tablets (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE myth_texts (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO tablets VALUES ('P1')")

    report = inspect_database(path)

    assert report.status == "healthy"
    assert report.schema == "legacy-v2"
    assert report.counts == {"myth_texts": 0, "tablets": 1}


def test_evidence_database_has_precedence_over_legacy_tables(tmp_path: Path) -> None:
    """Catches the new evidence schema being mislabeled when legacy tables coexist."""
    path = tmp_path / "evidence.db"
    ResearchStore(path).initialize()
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE tablets (id TEXT PRIMARY KEY)")

    report = inspect_database(path)

    assert report.status == "healthy"
    assert report.schema == "evidence-v1"


def test_partial_evidence_schema_is_not_healthy(tmp_path):
    path = tmp_path / "partial.db"
    with closing(sqlite3.connect(path)) as con:
        con.execute("CREATE TABLE artifacts (id TEXT PRIMARY KEY)")
        con.execute("CREATE TABLE source_snapshots (id TEXT PRIMARY KEY)")
    report = inspect_database(path)
    assert report.status == "degraded"
    assert "schema" in report.error


def test_non_sqlite_file_is_unavailable(tmp_path: Path) -> None:
    """Catches malformed input being reported as a healthy empty database."""
    path = tmp_path / "invalid.db"
    path.write_text("not sqlite", encoding="utf-8")

    report = inspect_database(path)

    assert report.status == "unavailable"
    assert report.error is not None
