"""The versioned SQLite table contract used by creation, open, health and restore."""

import re
import sqlite3
from functools import lru_cache

CREATE_SCHEMA = """
                BEGIN IMMEDIATE;
                CREATE TABLE source_snapshots (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, license TEXT NOT NULL,
                    checksum TEXT NOT NULL, adapter TEXT NOT NULL, raw BLOB NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE artifacts (id TEXT PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
                    UNIQUE(source, external_id));
                CREATE TABLE editions (id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    snapshot_id TEXT NOT NULL REFERENCES source_snapshots(id), record TEXT NOT NULL,
                    UNIQUE(artifact_id, snapshot_id));
                CREATE TABLE annotations (id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    kind TEXT NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, origin TEXT NOT NULL,
                    evidence TEXT NOT NULL, supersedes TEXT REFERENCES annotations(id), created_at TEXT NOT NULL);
                CREATE TABLE review_events (seq INTEGER PRIMARY KEY, annotation_id TEXT NOT NULL REFERENCES annotations(id),
                    decision TEXT NOT NULL CHECK(decision IN ('accepted','rejected')), actor TEXT NOT NULL,
                    reason TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE assets (id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    name TEXT NOT NULL, media_type TEXT NOT NULL, license TEXT NOT NULL, actor TEXT NOT NULL,
                    checksum TEXT NOT NULL, content BLOB NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE experiment_runs (id TEXT PRIMARY KEY, method TEXT NOT NULL,
                    inputs TEXT NOT NULL, outputs TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX editions_artifact ON editions(artifact_id);
                CREATE INDEX annotations_artifact ON annotations(artifact_id);
                CREATE INDEX reviews_annotation ON review_events(annotation_id, seq);
            """


def sql_tokens(sql):
    # Ignore formatting, but preserve quoted literals exactly (including whitespace).
    return tuple(re.findall(r"'(?:(?:'')|[^'])*'|\"(?:(?:\"\")|[^\"])*\"|\w+|[^\s]", sql))


@lru_cache(maxsize=1)
def expected_tables():
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(CREATE_SCHEMA)
        return {
            name: sql_tokens(sql)
            for name, sql in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()


def validate_tables(con):
    actual = dict(con.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
    for name, expected in expected_tables().items():
        if sql_tokens(actual.get(name, "")) != expected:
            raise ValueError(f"invalid project schema constraints: {name}")
