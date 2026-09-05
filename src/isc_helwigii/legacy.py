"""Read-only, bounded legacy ingestion. Legacy generated labels stay unreviewed."""

import sqlite3
from contextlib import closing
from pathlib import Path

from isc_helwigii.store import canonical


def import_legacy(store, path, *, source, license, limit=500):
    path = Path(path).expanduser().resolve()
    if (
        path == store.path
        or not path.is_file()
        or type(limit) is not int
        or not 1 <= limit <= 50000
    ):
        raise ValueError("existing separate legacy database and limit 1..50000 required")
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        columns = [r["name"] for r in con.execute("PRAGMA table_info(tablets)")]
        if not {"id", "transliteration"} <= set(columns):
            raise ValueError("supported legacy tablets table with id and transliteration required")
        rows = [dict(r) for r in con.execute("SELECT * FROM tablets ORDER BY id LIMIT ?", (limit,))]
    records = []
    for row in rows:
        records.append(
            {
                "external_id": str(row["id"]),
                "text": row.get("transliteration") or "",
                "language": row.get("language") or "unknown",
                "title": row.get("title") or str(row["id"]),
                "legacy": True,
                "legacy_metadata": row,
                "validation_status": "unreviewed legacy import",
            }
        )
    raw = canonical(
        {
            "source_file_name": path.name,
            "query": "SELECT * FROM tablets ORDER BY id LIMIT ?",
            "limit": limit,
            "columns": columns,
            "rows": rows,
        }
    ).encode()
    snapshot = store.import_records(
        raw, records, source=source, license=license, adapter="legacy-query-export-v1"
    )
    return {
        "snapshot_id": snapshot,
        "record_count": len(records),
        "selection_limit": limit,
        "status": "unreviewed legacy records; generated labels not promoted to annotations",
    }
