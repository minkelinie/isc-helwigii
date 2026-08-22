"""
Tests voor Ox-Stealth Pipeline.
Run: pytest -v
"""
from __future__ import annotations

import sqlite3
import json
import tempfile
from pathlib import Path
import pytest

from ox_stealth.pipeline import OxStealthPipeline, PipelineResult


@pytest.fixture
def temp_db() -> Path:
    """Maak een tijdelijke database voor test-isolatie."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    # Minimaal schema
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE spijkerschrift (
            id TEXT PRIMARY KEY, bron TEXT, titel TEXT,
            cuneiform TEXT, transliteratie TEXT,
            content_hash TEXT UNIQUE, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE transliteratie_norm (
            id TEXT PRIMARY KEY, spijkerschrift_id TEXT, transliteratie_ruw TEXT,
            transliteratie_norm TEXT, taal_heuristiek TEXT, taal_llm TEXT,
            taal_final TEXT, confidence REAL, lemma_glossa_json TEXT,
            opmerkingen TEXT, verwerkt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE motief_entiteit (
            id TEXT PRIMARY KEY, norm_id TEXT, motieven_json TEXT,
            entiteiten_json TEXT, samenvatting TEXT, confidence REAL,
            verwerkt_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE clusters (id TEXT PRIMARY KEY, cluster_label TEXT, motief_kern TEXT,
                               member_norm_ids_json TEXT, centroid_embedding BLOB,
                               gegenereerd_op TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
    """)
    conn.commit()
    conn.close()
    yield db_path
    db_path.unlink(missing_ok=True)


def test_health_check_empty(temp_db):
    pipeline = OxStealthPipeline(temp_db)
    health = pipeline.health_check()
    assert health["status"] == "degraded"
    assert health["tablets"] == 0


def test_health_check_with_data(temp_db):
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("INSERT INTO spijkerschrift (id, bron, titel, cuneiform, transliteratie, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
                ("TEST-1", "Test", "Test Tablet", "㐸㐐", "d ba-ba", "hash1"))
    cur.execute("INSERT INTO transliteratie_norm (id, spijkerschrift_id, transliteratie_ruw, transliteratie_norm, taal_final, confidence, lemma_glossa_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("NORM-TEST-1", "TEST-1", "d ba-ba", "d ba-ba", "Sumerisch", 0.9, "[]"))
    cur.execute("INSERT INTO motief_entiteit (id, norm_id, motieven_json, entiteiten_json, samenvatting, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                ("ME-TEST-1", "NORM-TEST-1", '["godsrecht"]', '[{"type": "god", "naam": "Enlil"}]', "Test", 0.9))
    conn.commit()
    conn.close()

    pipeline = OxStealthPipeline(temp_db)
    health = pipeline.health_check()
    assert health["status"] == "healthy"
    assert health["tablets"] == 1
    assert health["normalized"] == 1
    assert health["annotated"] == 1


def test_pipeline_result_dataclass():
    res = PipelineResult(10, 8, 6, 3, 12, Path("/tmp/export"))
    assert res.ingested == 10
    assert res.clusters == 3