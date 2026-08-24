#!/usr/bin/env python3
"""
BACKEND HEALTH CHECK — Comprehensive validation of I.S.C. Helwigii backend.
Validates SQLite integrity, FAISS index, embedding dimensions, polyphony catalog,
static assets, and API smoke test. Exits non-zero on any critical failure.
"""

from __future__ import annotations

import json
import logging
import sys
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).parent))

from backend_core import (
    BackendCore,
    BackendConfig,
    get_default_config,
    FAISS_AVAILABLE,
    SBERT_AVAILABLE,
)

log = logging.getLogger("health-check")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)


# ──────────────────────────────────────────────────────────────
# Result Types
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of a single health check."""
    name: str
    status: str  # 'pass', 'warn', 'fail'
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass(slots=True)
class HealthReport:
    """Aggregated health check report."""
    checks: list[CheckResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        level = logging.ERROR if result.status == "fail" else logging.WARNING if result.status == "warn" else logging.INFO
        log.log(level, f"[{result.status.upper()}] {result.name}: {result.message}")

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def overall_status(self) -> str:
        if self.failed > 0:
            return "fail"
        if self.warnings > 0:
            return "warn"
        return "pass"

    def finalize(self) -> None:
        self.completed_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.overall_status,
            "duration_ms": (self.completed_at or time.time()) - self.started_at * 1000,
            "summary": {
                "total": len(self.checks),
                "passed": self.passed,
                "warnings": self.warnings,
                "failed": self.failed,
            },
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "details": c.details,
                    "duration_ms": c.duration_ms,
                }
                for c in self.checks
            ],
        }


# ──────────────────────────────────────────────────────────────
# Check Functions
# ──────────────────────────────────────────────────────────────
def timed_check(name: str, fn, report: HealthReport, critical: bool = True) -> Any:
    """Run a check with timing and error handling."""
    start = time.perf_counter()
    try:
        result = fn()
        duration = (time.perf_counter() - start) * 1000
        if isinstance(result, CheckResult):
            report.add(CheckResult(
                name=name,
                status=result.status,
                message=result.message,
                details=result.details,
                duration_ms=duration,
            ))
        else:
            report.add(CheckResult(
                name=name,
                status="pass",
                message=str(result),
                duration_ms=duration,
            ))
        return result
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        report.add(CheckResult(
            name=name,
            status="fail" if critical else "warn",
            message=f"Check crashed: {e}",
            details={"exception": type(e).__name__, "traceback": str(e)},
            duration_ms=duration,
        ))
        return None


# ──────────────────────────────────────────────────────────────
# SQLite Checks
# ──────────────────────────────────────────────────────────────
def check_sqlite_integrity(backend: BackendCore) -> CheckResult:
    """Validate SQLite database integrity and schema."""
    with backend._db_pool.connect() as conn:
        cur = conn.cursor()

        # 1. Integrity check
        cur.execute("PRAGMA integrity_check")
        integrity = cur.fetchone()[0]
        if integrity != "ok":
            return CheckResult(
                "sqlite_integrity",
                "fail",
                f"Integrity check failed: {integrity}",
                {"integrity_result": integrity},
            )

        # 2. Required tables exist
        required_tables = [
            "tablets",
            "cuneiform_signs",
            "myth_texts",
            "motif_taxonomy",
            "motif_instances",
            "phylo_tree",
            "corpus_catalog",
            "polyphony_corrections",
            "prebaked_embeddings",
            "prebaked_sign_knowledge",
        ]
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cur.fetchall()}
        missing = [t for t in required_tables if t not in existing]
        if missing:
            return CheckResult(
                "sqlite_schema",
                "fail",
                f"Missing required tables: {missing}",
                {"missing_tables": missing, "existing_tables": list(existing)},
            )

        # 3. Row counts
        counts = {}
        for table in required_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cur.fetchone()[0]

        # 4. Foreign key check
        cur.execute("PRAGMA foreign_key_check")
        fk_violations = cur.fetchall()
        if fk_violations:
            return CheckResult(
                "sqlite_foreign_keys",
                "warn",
                f"Foreign key violations found: {len(fk_violations)}",
                {"violations": fk_violations[:10]},
            )

        # 5. Journal mode
        cur.execute("PRAGMA journal_mode")
        journal_mode = cur.fetchone()[0]

        return CheckResult(
            "sqlite_integrity",
            "pass",
            f"SQLite OK: {len(required_tables)} tables, {sum(counts.values())} total rows",
            {"table_counts": counts, "journal_mode": journal_mode, "fk_violations": len(fk_violations)},
        )


def check_indices(backend: BackendCore) -> CheckResult:
    """Verify key indices exist."""
    with backend._db_pool.connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
        indices = {row["name"]: row["sql"] for row in cur.fetchall()}

        required_indices = [
            "idx_tablets_period_provenance",
            "idx_signs_tablet_type_conf",
            "idx_embeddings_type_entry",
            "idx_corrections_sign_status",
            "idx_sign_knowledge_frequency",
        ]

        missing = [idx for idx in required_indices if idx not in indices]
        if missing:
            return CheckResult(
                "sqlite_indices",
                "warn",
                f"Missing performance indices: {missing}",
                {"missing": missing, "total_indices": len(indices)},
            )

        return CheckResult(
            "sqlite_indices",
            "pass",
            f"All {len(required_indices)} key indices present",
            {"total_indices": len(indices)},
        )


# ──────────────────────────────────────────────────────────────
# FAISS Checks
# ──────────────────────────────────────────────────────────────
def check_faiss_index(backend: BackendCore) -> CheckResult:
    """Validate FAISS index loads and is queryable."""
    if not FAISS_AVAILABLE:
        return CheckResult(
            "faiss_index",
            "warn",
            "FAISS not available in environment",
            {"available": False},
        )

    faiss_idx = backend.get_faiss_index()

    if not faiss_idx.is_loaded():
        return CheckResult(
            "faiss_index",
            "fail",
            "FAISS index not loaded or empty",
            {"loaded": False, "path": str(backend._config.faiss_index_path)},
        )

    # Test query
    try:
        test_vector = np.random.randn(faiss_idx.dim).astype(np.float32)
        distances, indices = faiss_idx.search(test_vector, k=min(5, faiss_idx.count))

        if len(distances) == 0 or len(indices) == 0:
            return CheckResult(
                "faiss_index",
                "fail",
                "FAISS search returned empty results",
                {"count": faiss_idx.count, "dim": faiss_idx.dim},
            )

        return CheckResult(
            "faiss_index",
            "pass",
            f"FAISS index operational: {faiss_idx.count} vectors, dim={faiss_idx.dim}",
            {
                "count": faiss_idx.count,
                "dim": faiss_idx.dim,
                "embedding_type": faiss_idx.embedding_type,
                "test_query_ok": True,
            },
        )
    except Exception as e:
        return CheckResult(
            "faiss_index",
            "fail",
            f"FAISS search failed: {e}",
            {"count": faiss_idx.count, "dim": faiss_idx.dim, "error": str(e)},
        )


def check_faiss_metadata_consistency(backend: BackendCore) -> CheckResult:
    """Verify FAISS metadata matches database embeddings."""
    if not FAISS_AVAILABLE:
        return CheckResult("faiss_meta_consistency", "warn", "FAISS not available", {})

    with backend._db_pool.connect() as conn:
        cur = conn.cursor()
        # FAISS only indexes corpus_catalog entries (integer IDs compatible with FAISS IndexIDMap)
        cur.execute("""
            SELECT COUNT(*) FROM prebaked_embeddings
            WHERE embedding_type LIKE 'text_%' AND entry_type = 'corpus_catalog'
        """)
        db_count = cur.fetchone()[0]

    faiss_idx = backend.get_faiss_index()
    if not faiss_idx.is_loaded():
        return CheckResult("faiss_meta_consistency", "fail", "FAISS index not loaded", {})

    if db_count != faiss_idx.count:
        return CheckResult(
            "faiss_meta_consistency",
            "warn",
            f"Count mismatch: DB has {db_count} corpus_catalog text embeddings, FAISS has {faiss_idx.count}",
            {"db_count": db_count, "faiss_count": faiss_idx.count},
        )

    return CheckResult(
        "faiss_meta_consistency",
        "pass",
        f"Counts consistent: {db_count} corpus_catalog embeddings indexed",
        {"db_count": db_count, "faiss_count": faiss_idx.count},
    )


# ──────────────────────────────────────────────────────────────
# Embedding Checks
# ──────────────────────────────────────────────────────────────
def check_embedding_dimensions(backend: BackendCore) -> CheckResult:
    """Validate embedding dimensions match expectations."""
    with backend._db_pool.connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT embedding_type, embedding_dim, COUNT(*) as cnt
            FROM prebaked_embeddings
            GROUP BY embedding_type, embedding_dim
        """)
        dims = cur.fetchall()

    if not dims:
        return CheckResult("embed_dims", "warn", "No embeddings in database", {})

    expected = {
        "text_sbert": 384,
        "text_tfidf_svd": 384,
        "visual_bovw": 256,
    }

    issues = []
    for row in dims:
        etype = row["embedding_type"]
        dim = row["embedding_dim"]
        if etype in expected and dim != expected[etype]:
            issues.append(f"{etype}: got {dim}, expected {expected[etype]}")

    if issues:
        return CheckResult(
            "embed_dims",
            "warn",
            f"Dimension mismatches: {'; '.join(issues)}",
            {"details": [dict(r) for r in dims], "issues": issues},
        )

    return CheckResult(
        "embed_dims",
        "pass",
        f"All {len(dims)} embedding types have correct dimensions",
        {"details": [dict(r) for r in dims]},
    )


def check_embedding_coverage(backend: BackendCore) -> CheckResult:
    """Check embedding coverage across corpus."""
    with backend._db_pool.connect() as conn:
        cur = conn.cursor()

        # Tablets with embeddings
        cur.execute("""
            SELECT COUNT(DISTINCT t.id)
            FROM tablets t
            JOIN prebaked_embeddings e ON e.entry_id = t.id AND e.entry_type = 'tablet'
        """)
        tablets_with_emb = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM tablets")
        total_tablets = cur.fetchone()[0]

        # Myth texts with embeddings
        cur.execute("""
            SELECT COUNT(DISTINCT m.id)
            FROM myth_texts m
            JOIN prebaked_embeddings e ON e.entry_id = m.id AND e.entry_type = 'myth_text'
        """)
        myths_with_emb = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM myth_texts")
        total_myths = cur.fetchone()[0]

    coverage_tablets = tablets_with_emb / max(total_tablets, 1) * 100
    coverage_myths = myths_with_emb / max(total_myths, 1) * 100

    status = "pass"
    if coverage_tablets < 50 or coverage_myths < 50:
        status = "warn"

    return CheckResult(
        "embedding_coverage",
        status,
        f"Embedding coverage: tablets {coverage_tablets:.0f}% ({tablets_with_emb}/{total_tablets}), myths {coverage_myths:.0f}% ({myths_with_emb}/{total_myths})",
        {
            "tablets_with_embeddings": tablets_with_emb,
            "total_tablets": total_tablets,
            "myths_with_embeddings": myths_with_emb,
            "total_myths": total_myths,
        },
    )


# ──────────────────────────────────────────────────────────────
# Polyphony Checks
# ──────────────────────────────────────────────────────────────
def check_polyphony_catalog(backend: BackendCore) -> CheckResult:
    """Validate polyphony catalog completeness."""
    stats = backend.get_polyphony_engine().get_stats()

    issues = []
    if stats.get("total_signs", 0) < 50:
        issues.append(f"Only {stats.get('total_signs')} signs (expected 50+)")
    if stats.get("total_context_rules", 0) < 20:
        issues.append(f"Only {stats.get('total_context_rules')} context rules (expected 20+)")
    if stats.get("total_compounds", 0) < 10:
        issues.append(f"Only {stats.get('total_compounds')} compounds (expected 10+)")

    status = "fail" if issues and stats.get("total_signs", 0) == 0 else "warn" if issues else "pass"
    msg = "Polyphony catalog OK" if not issues else f"Polyphony issues: {'; '.join(issues)}"

    return CheckResult(
        "polyphony_catalog",
        status,
        msg,
        {"stats": stats, "issues": issues},
    )


def check_polyphony_json_consistency(backend: BackendCore) -> CheckResult:
    """Verify polyphony JSON file matches database."""
    poly_path = backend._config.polyphony_path
    if not poly_path.exists():
        return CheckResult(
            "polyphony_json",
            "warn",
            f"Polyphony JSON not found at {poly_path}",
            {"path": str(poly_path)},
        )

    with open(poly_path, "r") as f:
        data = json.load(f)

    json_signs = len(data.get("signs", {}))
    db_signs = backend.get_polyphony_engine().get_stats().get("total_signs", 0)

    if json_signs != db_signs:
        return CheckResult(
            "polyphony_json",
            "warn",
            f"Sign count mismatch: JSON={json_signs}, DB engine={db_signs}",
            {"json_signs": json_signs, "engine_signs": db_signs},
        )

    return CheckResult(
        "polyphony_json",
        "pass",
        f"Polyphony JSON consistent: {json_signs} signs",
        {"json_signs": json_signs, "training_stats": data.get("training_stats", {})},
    )


def check_active_learning(backend: BackendCore) -> CheckResult:
    """Check active learning pipeline."""
    al = backend.get_active_learning()
    stats = al.get_stats()

    return CheckResult(
        "active_learning",
        "pass",
        f"Active learning: {stats['pending']} pending, {stats['approved']} approved, {stats['rejected']} rejected",
        stats,
    )


# ──────────────────────────────────────────────────────────────
# Sign Knowledge Checks
# ──────────────────────────────────────────────────────────────
def check_sign_knowledge(backend: BackendCore) -> CheckResult:
    """Validate sign knowledge base."""
    knowledge = backend.sign_knowledge.get_all()

    if not knowledge:
        return CheckResult("sign_knowledge", "fail", "No sign knowledge entries found", {})

    with_unicode = sum(1 for k in knowledge if k.unicode)
    with_borger = sum(1 for k in knowledge if k.borger_number)
    with_readings = sum(1 for k in knowledge if k.sumerian_readings or k.akkadian_readings)

    issues = []
    if with_unicode < len(knowledge) * 0.8:
        issues.append(f"Only {with_unicode}/{len(knowledge)} have Unicode")
    if with_borger < len(knowledge) * 0.5:
        issues.append(f"Only {with_borger}/{len(knowledge)} have Borger numbers")

    status = "warn" if issues else "pass"
    msg = "Sign knowledge OK" if not issues else f"Sign knowledge issues: {'; '.join(issues)}"

    return CheckResult(
        "sign_knowledge",
        status,
        msg,
        {
            "total": len(knowledge),
            "with_unicode": with_unicode,
            "with_borger": with_borger,
            "with_readings": with_readings,
        },
    )


# ──────────────────────────────────────────────────────────────
# Static Assets Checks
# ──────────────────────────────────────────────────────────────
def check_static_assets() -> CheckResult:
    """Verify required static assets exist."""
    base = Path(__file__).parent
    required = [
        "app.py",
        "polyphony_engine.py",
        "train_polyphony_engine.py",
        "precompute_global_embeddings.py",
        "download_prebaked_knowledge.py",
        "corpus_registry.py",
        "sign_detection_engine.py",
        "phylomythology_engine.py",
        "README.md",
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
    ]

    missing = [f for f in required if not (base / f).exists()]

    if missing:
        return CheckResult(
            "static_assets",
            "fail",
            f"Missing required files: {missing}",
            {"missing": missing},
        )

    # Check export directory
    export_dir = Path("/data/export") if Path("/data/export").exists() else base / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    return CheckResult(
        "static_assets",
        "pass",
        f"All {len(required)} static assets present",
        {"export_dir": str(export_dir)},
    )


# ──────────────────────────────────────────────────────────────
# Bayesian Disambiguation Smoke Test
# ──────────────────────────────────────────────────────────────
def check_bayesian_disambiguation(backend: BackendCore) -> CheckResult:
    """Smoke test Bayesian disambiguation."""
    bayesian = backend.get_bayesian_disambiguator()

    # Test with a known sign
    result = bayesian.disambiguate("AN", ["KI", "LUGAL"])

    if not result.readings:
        return CheckResult(
            "bayesian_disambiguation",
            "warn",
            "Bayesian disambiguation returned no readings",
            {"sign_id": "AN", "context": ["KI", "LUGAL"]},
        )

    return CheckResult(
        "bayesian_disambiguation",
        "pass",
        f"Bayesian disambiguation works: {len(result.readings)} readings for AN, best={result.best_reading} (conf={result.confidence:.2f})",
        {
            "sign_id": "AN",
            "top_readings": list(result.readings.items())[:3],
            "best": result.best_reading,
            "confidence": result.confidence,
        },
    )


def check_sequence_disambiguation(backend: BackendCore) -> CheckResult:
    """Test sequence disambiguation."""
    bayesian = backend.get_bayesian_disambiguator()
    results = bayesian.disambiguate_sequence(["AN", "KI", "LUGAL", "EN"])

    if len(results) != 4:
        return CheckResult(
            "sequence_disambiguation",
            "fail",
            f"Expected 4 results, got {len(results)}",
            {},
        )

    return CheckResult(
        "sequence_disambiguation",
        "pass",
        f"Sequence disambiguation works for {len(results)} signs",
        {"results": [(r.sign_id, r.best_reading, f"{r.confidence:.2f}") for r in results]},
    )


# ──────────────────────────────────────────────────────────────
# API Smoke Test
# ──────────────────────────────────────────────────────────────
def check_api_smoke_test(backend: BackendCore) -> CheckResult:
    """Test Streamlit app can import without errors."""
    try:
        # Import app module to check for import errors
        import app
        return CheckResult(
            "api_smoke_import",
            "pass",
            "Streamlit app imports successfully",
            {},
        )
    except Exception as e:
        return CheckResult(
            "api_smoke_import",
            "fail",
            f"Streamlit app import failed: {e}",
            {"error": str(e)},
        )


def check_docker_build() -> CheckResult:
    """Verify Dockerfile builds (optional, may take long)."""
    dockerfile = Path(__file__).parent / "Dockerfile"
    if not dockerfile.exists():
        return CheckResult("docker_build", "warn", "Dockerfile not found", {})

    # Quick syntax check only
    content = dockerfile.read_text()
    required = ["FROM python:3.11-slim", "opencv", "streamlit", "HEALTHCHECK"]
    missing = [r for r in required if r not in content]

    if missing:
        return CheckResult(
            "docker_build",
            "warn",
            f"Dockerfile missing key elements: {missing}",
            {"missing": missing},
        )

    return CheckResult(
        "docker_build",
        "pass",
        "Dockerfile has required elements",
        {},
    )


def check_requirements_txt() -> CheckResult:
    """Verify requirements.txt is in sync with pyproject.toml."""
    req_path = Path(__file__).parent / "requirements.txt"
    pyproject_path = Path(__file__).parent / "pyproject.toml"

    if not req_path.exists():
        return CheckResult("requirements_txt", "warn", "requirements.txt not found", {})

    try:
        import toml
        pyproject = toml.load(pyproject_path)
        pydeps_raw = pyproject.get("project", {}).get("dependencies", [])

        # Normalize pyproject deps to lowercase package names (without version specifiers)
        pydeps = set()
        for dep in pydeps_raw:
            pkg = dep.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip().lower()
            pydeps.add(pkg)

        req_deps = set()
        for line in req_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # Extract package name (before version specifier)
                pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip().lower()
                req_deps.add(pkg)

        missing_in_req = pydeps - req_deps
        extra_in_req = req_deps - pydeps

        if missing_in_req or extra_in_req:
            return CheckResult(
                "requirements_txt",
                "warn",
                f"Sync issues: missing in req={missing_in_req}, extra in req={extra_in_req}",
                {"missing": list(missing_in_req), "extra": list(extra_in_req)},
            )

        return CheckResult(
            "requirements_txt",
            "pass",
            f"requirements.txt in sync with pyproject.toml ({len(pydeps)} deps)",
            {"count": len(pydeps)},
        )
    except Exception as e:
        return CheckResult("requirements_txt", "warn", f"Could not verify sync: {e}", {})


# ──────────────────────────────────────────────────────────────
# Corpus Registry Checks
# ──────────────────────────────────────────────────────────────
def check_corpus_registry(backend: BackendCore) -> CheckResult:
    """Verify corpus catalog has data."""
    with backend._db_pool.connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM corpus_catalog")
        count = cur.fetchone()[0]

        cur.execute("SELECT DISTINCT source_corpus FROM corpus_catalog")
        sources = [row[0] for row in cur.fetchall()]

    if count == 0:
        return CheckResult(
            "corpus_registry",
            "warn",
            "Corpus catalog is empty (run corpus_registry.py)",
            {"count": 0},
        )

    expected_sources = {"CDLI", "ORACC", "ETCSL"}
    present = set(sources)
    missing_sources = expected_sources - present

    status = "warn" if missing_sources else "pass"
    msg = f"Corpus catalog: {count} entries from {len(sources)} sources"
    if missing_sources:
        msg += f" (missing: {missing_sources})"

    return CheckResult(
        "corpus_registry",
        status,
        msg,
        {"count": count, "sources": sources, "missing_expected": list(missing_sources)},
    )


# ──────────────────────────────────────────────────────────────
# Phylomythology Checks
# ──────────────────────────────────────────────────────────────
def check_phylomythology(backend: BackendCore) -> CheckResult:
    """Verify phylomythology data loaded."""
    with backend._db_pool.connect() as conn:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM myth_texts")
        myths = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM motif_instances")
        motifs = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM phylo_tree")
        tree_nodes = cur.fetchone()[0]

    if myths == 0:
        return CheckResult("phylomythology", "fail", "No myth texts loaded", {})

    return CheckResult(
        "phylomythology",
        "pass",
        f"Phylomythology loaded: {myths} myths, {motifs} motif instances, {tree_nodes} tree nodes",
        {"myths": myths, "motif_instances": motifs, "tree_nodes": tree_nodes},
    )


# ──────────────────────────────────────────────────────────────
# Export Functionality Check
# ──────────────────────────────────────────────────────────────
def check_export_directory(backend: BackendCore) -> CheckResult:
    """Verify export directory is writable."""
    export_dir = Path("/data/export") if Path("/data/export").exists() else Path(__file__).parent / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    test_file = export_dir / ".health_check_write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
        return CheckResult(
            "export_directory",
            "pass",
            f"Export directory writable: {export_dir}",
            {"path": str(export_dir)},
        )
    except Exception as e:
        return CheckResult(
            "export_directory",
            "fail",
            f"Export directory not writable: {e}",
            {"path": str(export_dir), "error": str(e)},
        )


# ──────────────────────────────────────────────────────────────
# Knowledge Auto-Fetch Check
# ──────────────────────────────────────────────────────────────
def check_knowledge_fetch(backend: BackendCore) -> CheckResult:
    """Verify knowledge auto-fetch mechanism."""
    from download_prebaked_knowledge import ensure_knowledge_available, load_state

    state = load_state()
    version = state.get("version")

    if not version:
        return CheckResult(
            "knowledge_fetch",
            "warn",
            "Knowledge state not initialized (first run will auto-fetch)",
            {"state": state},
        )

    required_files = ["cuneiform_polyphony.json", "prebaked_sign_knowledge.json"]
    missing = [f for f in required_files if not (Path("/data") / f).exists()]

    if missing:
        return CheckResult(
            "knowledge_fetch",
            "warn",
            f"Missing knowledge files: {missing}",
            {"missing": missing, "version": version},
        )

    return CheckResult(
        "knowledge_fetch",
        "pass",
        f"Knowledge at version {version}, all files present",
        {"version": version, "files": required_files},
    )


# ──────────────────────────────────────────────────────────────
# Main Health Check Runner
# ──────────────────────────────────────────────────────────────
def run_all_checks(config: Optional[BackendConfig] = None) -> HealthReport:
    """Run all health checks and return report."""
    report = HealthReport()

    # Initialize backend
    backend = BackendCore(config)

    try:
        log.info("Starting backend health checks...")

        # Core infrastructure
        timed_check("sqlite_integrity", lambda: check_sqlite_integrity(backend), report)
        timed_check("sqlite_indices", lambda: check_indices(backend), report)

        # FAISS
        timed_check("faiss_index", lambda: check_faiss_index(backend), report)
        timed_check("faiss_meta_consistency", lambda: check_faiss_metadata_consistency(backend), report)

        # Embeddings
        timed_check("embedding_dimensions", lambda: check_embedding_dimensions(backend), report)
        timed_check("embedding_coverage", lambda: check_embedding_coverage(backend), report, critical=False)

        # Polyphony
        timed_check("polyphony_catalog", lambda: check_polyphony_catalog(backend), report)
        timed_check("polyphony_json_consistency", lambda: check_polyphony_json_consistency(backend), report)
        timed_check("active_learning", lambda: check_active_learning(backend), report)

        # Sign knowledge
        timed_check("sign_knowledge", lambda: check_sign_knowledge(backend), report)

        # Bayesian
        timed_check("bayesian_disambiguation", lambda: check_bayesian_disambiguation(backend), report)
        timed_check("sequence_disambiguation", lambda: check_sequence_disambiguation(backend), report)

        # Static assets & config
        timed_check("static_assets", check_static_assets, report)
        timed_check("docker_build", check_docker_build, report, critical=False)
        timed_check("requirements_txt", check_requirements_txt, report, critical=False)

        # Data pipelines
        timed_check("corpus_registry", lambda: check_corpus_registry(backend), report, critical=False)
        timed_check("phylomythology", lambda: check_phylomythology(backend), report)

        # Export & knowledge
        timed_check("export_directory", lambda: check_export_directory(backend), report)
        timed_check("knowledge_fetch", lambda: check_knowledge_fetch(backend), report, critical=False)

        # API smoke test
        timed_check("api_smoke_import", lambda: check_api_smoke_test(backend), report)

    finally:
        backend.close()

    report.finalize()
    return report


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────
def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="I.S.C. Helwigii Backend Health Check")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--config-db", type=Path, help="Custom database path")
    parser.add_argument("--fail-on-warn", action="store_true", help="Exit non-zero on warnings")
    parser.add_argument("--output", type=Path, help="Write JSON report to file")
    args = parser.parse_args()

    config = None
    if args.config_db:
        config = BackendConfig(
            db_path=args.config_db,
            prebaked_dir=args.config_db.parent / "prebaked_embeddings",
            polyphony_path=args.config_db.parent / "cuneiform_polyphony.json",
        )

    report = run_all_checks(config)

    if args.json or args.output:
        output_data = json.dumps(report.to_dict(), indent=2, default=str)
        if args.output:
            args.output.write_text(output_data)
            log.info(f"Report written to {args.output}")
        if args.json:
            print(output_data)

    # Print summary
    print(f"\n{'='*60}")
    print(f"HEALTH CHECK SUMMARY: {report.overall_status.upper()}")
    print(f"{'='*60}")
    print(f"Passed:  {report.passed}")
    print(f"Warnings: {report.warnings}")
    print(f"Failed:  {report.failed}")
    print(f"Total:   {len(report.checks)}")
    print(f"Duration: {(report.completed_at - report.started_at)*1000:.0f}ms")
    print(f"{'='*60}\n")

    # Exit code logic
    if report.failed > 0:
        return 1
    if args.fail_on_warn and report.warnings > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())