"""
Hoofd-pipeline orchestratie — herbruikbaar voor tests, CLI & CI.
"""
from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any

log = logging.getLogger("ox-stealth.pipeline")


@dataclass
class PipelineResult:
    ingested: int
    normalized: int
    annotated: int
    clusters: int
    similarities: int
    export_path: Path


class OxStealthPipeline:
    def __init__(self, db_path: Path = Path("/data/cuneiform_master.db")):
        self.db_path = db_path

    def run_full(self) -> PipelineResult:
        """Voer volledige pipeline uit (ingest → norm → myth → viz)."""
        # Import hier om cirkel-imports te vermijden
        from run_me import run_pipeline as ingest
        from run_me_2 import run_normalisatie as normalize
        from run_me_3 import run_myth_hunter as myth
        from run_me_4 import run_dashboard_pipeline as viz

        log.info("START FULL PIPELINE")
        ingest_stats = ingest()
        norm_stats = normalize()
        myth_stats = myth()
        viz()  # geen return stats
        log.info("FULL PIPELINE COMPLETE")

        return PipelineResult(
            ingested=ingest_stats.get("total", 0),
            normalized=norm_stats.get("verwerkt", 0),
            annotated=myth_stats.get("llm_extracted", 0),
            clusters=myth_stats.get("clusters", 0),
            similarities=myth_stats.get("similariteiten", 0),
            export_path=Path("/data/export"),
        )

    def health_check(self) -> Dict[str, Any]:
        """Lightweight check voor monitoring/load balancer."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM spijkerschrift")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM transliteratie_norm")
        norm = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM motief_entiteit")
        ann = cur.fetchone()[0]
        conn.close()
        return {
            "status": "healthy" if total > 0 else "degraded",
            "tablets": total,
            "normalized": norm,
            "annotated": ann,
        }