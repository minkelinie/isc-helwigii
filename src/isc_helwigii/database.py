"""Read-only database inspection for runtime and deployment health checks."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

KNOWN_TABLES = (
    "artifacts",
    "source_snapshots",
    "tablets",
    "myth_texts",
    "spijkerschrift",
)


@dataclass(frozen=True, slots=True)
class DatabaseReport:
    """A non-mutating summary of a recognized or legacy database."""

    status: str
    path: Path
    schema: str
    tables: tuple[str, ...]
    counts: dict[str, int]
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""
        payload = asdict(self)
        payload["path"] = str(self.path)
        payload["tables"] = list(self.tables)
        return payload


def _classify_schema(tables: set[str]) -> str:
    if {"artifacts", "source_snapshots"}.issubset(tables):
        return "evidence-v1"
    if "tablets" in tables:
        return "legacy-v2"
    if "spijkerschrift" in tables:
        return "legacy-v1"
    return "unknown"


def inspect_database(path: Path) -> DatabaseReport:
    """Inspect an existing SQLite database without creating or modifying it."""
    if not path.exists():
        return DatabaseReport(
            status="unavailable",
            path=path,
            schema="unknown",
            tables=(),
            counts={},
            error="database does not exist",
        )

    connection: sqlite3.Connection | None = None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        rows = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        tables = {str(row[0]) for row in rows}
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in KNOWN_TABLES
            if table in tables
        }
        schema = _classify_schema(tables)
        return DatabaseReport(
            status="healthy" if schema != "unknown" else "degraded",
            path=path,
            schema=schema,
            tables=tuple(sorted(tables)),
            counts=counts,
        )
    except (OSError, sqlite3.Error) as exc:
        return DatabaseReport(
            status="unavailable",
            path=path,
            schema="unknown",
            tables=(),
            counts={},
            error=str(exc),
        )
    finally:
        if connection is not None:
            connection.close()
