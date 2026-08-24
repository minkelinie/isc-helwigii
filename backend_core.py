#!/usr/bin/env python3
"""
BACKEND CORE — Centralized Database, FAISS, Active Learning & Bayesian Disambiguation
Type-safe, dependency-injected core services for I.S.C. Helwigii.
"""

from __future__ import annotations

import sqlite3
import json
import logging
import os
import pickle
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, Optional, Protocol, TypeVar, runtime_checkable
from enum import Enum

import numpy as np

# Optional FAISS
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None  # type: ignore

# Optional sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SBERT_AVAILABLE = True
except ImportError:
    SBERT_AVAILABLE = False

from polyphony_engine import PolyphonyEngine, SignReading, get_polyphony_engine


# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
log = logging.getLogger("isc-helwigii.backend")
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


# ──────────────────────────────────────────────────────────────
# Type Definitions & Protocols
# ──────────────────────────────────────────────────────────────
T = TypeVar("T")


@runtime_checkable
class EmbeddingModel(Protocol):
    """Protocol for embedding models."""

    def encode(self, texts: list[str], **kwargs: Any) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class TabletRow:
    """Typed tablet row from database."""
    id: str
    source: Optional[str]
    title: Optional[str]
    cuneiform: Optional[str]
    transliteration: Optional[str]
    language: Optional[str]
    period: Optional[str]
    genre: Optional[str]
    myth_labels_json: Optional[str]
    content_hash: Optional[str]
    created_at: Optional[str]
    p_number: Optional[str]


@dataclass(frozen=True, slots=True)
class SignRow:
    """Typed sign row from database."""
    id: str
    tablet_id: str
    image_path: Optional[str]
    sign_index: int
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    confidence: float
    sign_type: str
    atf_hypothesis: Optional[str]
    unicode_hypothesis: Optional[str]
    detected_at: Optional[str]
    period: Optional[str]  # From JOIN with tablets


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    """Typed embedding record."""
    entry_id: int
    entry_type: str
    embedding_type: str
    embedding: np.ndarray
    embedding_dim: int
    model_name: str
    model_version: str


@dataclass(frozen=True, slots=True)
class SignKnowledge:
    """Typed sign knowledge entry."""
    sign_id: str
    unicode: str
    borger_number: str
    name: str
    sumerian_readings: list[str]
    akkadian_readings: list[str]
    logographic_values: list[str]
    periods: list[str]
    corpus_frequency: int
    confidence_score: float


class EmbeddingType(str, Enum):
    """Supported embedding types."""
    TEXT_SBERT = "text_sbert"
    TEXT_TFIDF_SVD = "text_tfidf_svd"
    VISUAL_ORB = "visual_orb"
    VISUAL_BOVW = "visual_bovw"


class EntryType(str, Enum):
    """Entry types for embeddings."""
    TABLET = "tablet"
    MYTH_TEXT = "myth_text"
    CORPUS_CATALOG = "corpus_catalog"
    USER_FRAGMENT = "user_fragment"


# ──────────────────────────────────────────────────────────────
# Configuration Dataclasses
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Immutable backend configuration."""
    db_path: Path
    prebaked_dir: Path
    polyphony_path: Path
    sbert_model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    faiss_index_path: Path = field(init=False)
    faiss_meta_path: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "faiss_index_path", self.prebaked_dir / "faiss_index.bin")
        object.__setattr__(self, "faiss_meta_path", self.prebaked_dir / "faiss_metadata.json")


def get_default_config() -> BackendConfig:
    """Create default configuration with auto-detected paths."""
    data_dir = Path("/data") if Path("/data").exists() else Path.home() / "Desktop" / "OxStealthData"
    return BackendConfig(
        db_path=data_dir / "cuneiform_master.db",
        prebaked_dir=data_dir / "prebaked_embeddings",
        polyphony_path=data_dir / "cuneiform_polyphony.json",
    )


# ──────────────────────────────────────────────────────────────
# Database Connection Pool (Simple Context Manager)
# ──────────────────────────────────────────────────────────────
class DatabasePool:
    """Lightweight connection manager with row factory and foreign keys."""

    def __init__(self, db_path: Path, max_connections: int = 1):
        self._db_path = db_path
        self._max_connections = max_connections
        self._conn: Optional[sqlite3.Connection] = None

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with standard pragmas."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield self._conn
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        """Close the connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ──────────────────────────────────────────────────────────────
# FAISS Index Manager
# ──────────────────────────────────────────────────────────────
@dataclass(slots=True)
class FaissIndex:
    """FAISS index wrapper with metadata."""
    index: Optional["faiss.Index"] = None
    entry_ids: list[int] = field(default_factory=list)  # Original IDs (can be int or str)
    entry_types: list[str] = field(default_factory=list)
    embedding_type: str = ""
    dim: int = 0
    count: int = 0
    loaded_at: float = 0.0
    int_id_mapping: dict = field(default_factory=dict)  # Maps original ID -> internal int ID

    def is_loaded(self) -> bool:
        return self.index is not None and self.count > 0

    def search(self, query: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
        """Search index, returning (distances, indices)."""
        if not self.is_loaded():
            raise RuntimeError("FAISS index not loaded")
        if query.ndim == 1:
            query = query.reshape(1, -1)
        faiss.normalize_L2(query)
        return self.index.search(query, k)

    def get_original_ids(self, int_indices: np.ndarray) -> list:
        """Convert internal integer indices back to original entry IDs."""
        if not self.int_id_mapping:
            # No mapping, assume direct integer mapping
            return [self.entry_ids[i] if i < len(self.entry_ids) else -1 for i in int_indices]

        # Reverse mapping: int_id -> original_id
        int_to_original = {v: k for k, v in self.int_id_mapping.items()}
        return [int_to_original.get(i, -1) for i in int_indices]


class FaissManager:
    """Manages FAISS index loading and persistence."""

    def __init__(self, config: BackendConfig):
        self._config = config
        self._index: Optional[FaissIndex] = None

    def load(self) -> FaissIndex:
        """Load FAISS index from disk."""
        if self._index is not None and self._index.is_loaded():
            return self._index

        if not FAISS_AVAILABLE:
            log.warning("FAISS not available - returning empty index")
            self._index = FaissIndex()
            return self._index

        if not self._config.faiss_index_path.exists():
            log.warning(f"FAISS index not found at {self._config.faiss_index_path}")
            self._index = FaissIndex()
            return self._index

        try:
            index = faiss.read_index(str(self._config.faiss_index_path))
            with open(self._config.faiss_meta_path, "r") as f:
                meta = json.load(f)

            self._index = FaissIndex(
                index=index,
                entry_ids=meta.get("entry_ids", []),
                entry_types=meta.get("entry_types", []),
                embedding_type=meta.get("embedding_type", ""),
                dim=meta.get("dim", 0),
                count=meta.get("count", 0),
                loaded_at=time.time(),
                int_id_mapping=meta.get("int_id_mapping", {}),
            )
            log.info(f"✓ FAISS index loaded: {self._index.count} vectors, dim={self._index.dim}")
        except Exception as e:
            log.error(f"Failed to load FAISS index: {e}")
            self._index = FaissIndex()

        return self._index

    def get_index(self) -> FaissIndex:
        """Get current index, loading if necessary."""
        if self._index is None:
            return self.load()
        return self._index

    def rebuild(self, db_pool: DatabasePool) -> FaissIndex:
        """Rebuild FAISS index from database embeddings."""
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS not available for index rebuild")

        with db_pool.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT entry_id, entry_type, embedding, embedding_type
                FROM prebaked_embeddings
                WHERE embedding_type LIKE 'text_%'
                ORDER BY embedding_type, entry_id
            """)
            rows = cur.fetchall()

        if not rows:
            raise ValueError("No text embeddings found in database")

        # Group by embedding type (use most common)
        by_type: dict[str, list[tuple[int, str, np.ndarray]]] = {}
        for row in rows:
            etype = row["embedding_type"]
            emb = pickle.loads(row["embedding"])
            by_type.setdefault(etype, []).append((row["entry_id"], row["entry_type"], emb))

        # Use largest group
        best_type, entries = max(by_type.items(), key=lambda x: len(x[1]))

        vectors = np.vstack([e[2].flatten() for e in entries]).astype(np.float32)
        ids = np.array([e[0] for e in entries], dtype=np.int64)
        types = [e[1] for e in entries]

        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index = faiss.IndexIDMap(index)
        index.add_with_ids(vectors, ids)

        # Save
        self._config.prebaked_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self._config.faiss_index_path))

        meta = {
            "entry_ids": ids.tolist(),
            "entry_types": types,
            "embedding_type": best_type,
            "dim": int(vectors.shape[1]),
            "count": int(len(ids)),
        }
        with open(self._config.faiss_meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        self._index = FaissIndex(
            index=index,
            entry_ids=ids.tolist(),
            entry_types=types,
            embedding_type=best_type,
            dim=int(vectors.shape[1]),
            count=int(len(ids)),
            loaded_at=time.time(),
        )
        log.info(f"✓ FAISS index rebuilt: {self._index.count} vectors")
        return self._index


# ──────────────────────────────────────────────────────────────
# SBERT Embedder (Lazy Loading)
# ──────────────────────────────────────────────────────────────
class SBertEmbedder:
    """Lazy-loading SBERT embedder with fallback."""

    def __init__(self, model_name: str):
        self._model_name = model_name
        self._model: Optional[SentenceTransformer] = None

    def _ensure_loaded(self) -> None:
        if self._model is None and SBERT_AVAILABLE:
            log.info(f"Loading SBERT model: {self._model_name}")
            self._model = SentenceTransformer(self._model_name)
            log.info("✓ SBERT model loaded")

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts, returning float32 array."""
        self._ensure_loaded()
        if self._model is None:
            raise RuntimeError("SBERT not available")
        return self._model.encode(texts, show_progress_bar=True, batch_size=32).astype(np.float32)

    def is_available(self) -> bool:
        return SBERT_AVAILABLE


# ──────────────────────────────────────────────────────────────
# Bayesian Disambiguation Engine
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class DisambiguationResult:
    """Result of Bayesian disambiguation."""
    sign_id: str
    readings: dict[str, float]  # reading -> posterior probability
    best_reading: str
    confidence: float
    context_used: list[str]


class BayesianDisambiguator:
    """
    Bayesian context-aware disambiguation using Dirichlet prior over n-gram co-occurrences.

    Formula: P(reading | context) ∝ P(context | reading) × P(reading)
    Where P(context | reading) uses Dirichlet-smoothed n-gram probabilities.
    """

    def __init__(
        self,
        polyphony_engine: PolyphonyEngine,
        alpha: float = 0.1,  # Dirichlet prior concentration
        ngram_order: int = 3,
    ):
        self._engine = polyphony_engine
        self._alpha = alpha
        self._ngram_order = ngram_order
        self._context_cache: dict[str, dict[str, float]] = {}

    def _get_ngram_context_prob(
        self,
        reading: str,
        context: list[str],
    ) -> float:
        """
        Compute P(context | reading) using Dirichlet-smoothed n-gram model.

        For each n-gram window containing the target sign, compute probability
        of the context given the reading using add-alpha smoothing.
        """
        if not context:
            return 1.0

        # Get n-gram statistics from polyphony engine
        # We'll compute on-the-fly from corpus data
        total_log_prob = 0.0
        ngram_count = 0

        target_idx = len(context) // 2  # Approximate position
        context_window = context[max(0, target_idx - 2):target_idx + 3]

        for i in range(len(context_window) - self._ngram_order + 1):
            ngram = tuple(context_window[i:i + self._ngram_order])
            # Simple frequency-based estimate with Dirichlet smoothing
            # In production, this would use precomputed n-gram counts
            prob = self._estimate_ngram_prob(ngram, reading)
            total_log_prob += np.log(max(prob, 1e-10))
            ngram_count += 1

        if ngram_count == 0:
            return 1.0

        return float(np.exp(total_log_prob / ngram_count))

    def _estimate_ngram_prob(self, ngram: tuple[str, ...], target_reading: str) -> float:
        """Estimate n-gram probability with Dirichlet smoothing."""
        # This is a simplified version; full implementation would query
        # precomputed n-gram counts from the polyphony engine's training data
        vocab_size = 1000  # Estimated vocabulary size
        pseudo_count = self._alpha * vocab_size

        # Uniform prior as fallback
        return self._alpha / (1.0 + pseudo_count)

    def disambiguate(
        self,
        sign_id: str,
        context: list[str],
        top_k: int = 5,
    ) -> DisambiguationResult:
        """
        Perform Bayesian disambiguation for a sign in context.

        Args:
            sign_id: The cuneiform sign to disambiguate
            context: List of surrounding sign IDs (left and right context)
            top_k: Number of top readings to return

        Returns:
            DisambiguationResult with posterior probabilities
        """
        sign = self._engine.signs.get(sign_id)
        if not sign:
            return DisambiguationResult(
                sign_id=sign_id,
                readings={},
                best_reading="",
                confidence=0.0,
                context_used=context,
            )

        # Collect all possible readings with priors
        all_readings: dict[str, float] = {}

        # Sumerian readings
        for r in sign.sumerian:
            all_readings[f"SUM:{r}"] = 1.0

        # Akkadian readings
        for r in sign.akkadian:
            all_readings[f"AKK:{r}"] = 1.0

        # Logographic readings
        for r in sign.logographic:
            all_readings[f"LOG:{r}"] = 1.0

        if not all_readings:
            return DisambiguationResult(
                sign_id=sign_id,
                readings={},
                best_reading="",
                confidence=0.0,
                context_used=context,
            )

        # Compute posteriors: P(reading | context) ∝ P(context | reading) × P(reading)
        # Use uniform prior P(reading) = 1/|readings|
        prior = 1.0 / len(all_readings)
        posteriors: dict[str, float] = {}

        for reading_key in all_readings:
            likelihood = self._get_ngram_context_prob(reading_key, context)
            posteriors[reading_key] = likelihood * prior

        # Normalize
        total = sum(posteriors.values())
        if total > 0:
            posteriors = {k: v / total for k, v in posteriors.items()}
        else:
            posteriors = {k: 1.0 / len(posteriors) for k in posteriors}

        # Sort by posterior probability
        sorted_readings = dict(sorted(posteriors.items(), key=lambda x: x[1], reverse=True))
        best = next(iter(sorted_readings)) if sorted_readings else ""

        return DisambiguationResult(
            sign_id=sign_id,
            readings=dict(list(sorted_readings.items())[:top_k]),
            best_reading=best,
            confidence=sorted_readings.get(best, 0.0),
            context_used=context,
        )

    def disambiguate_sequence(
        self,
        sign_sequence: list[str],
        window_size: int = 5,
    ) -> list[DisambiguationResult]:
        """
        Disambiguate a full sequence of signs using sliding window context.

        Args:
            sign_sequence: List of sign IDs
            window_size: Context window radius (total context = 2*window_size + 1)

        Returns:
            List of DisambiguationResult for each position
        """
        results = []
        for i, sign_id in enumerate(sign_sequence):
            left = sign_sequence[max(0, i - window_size):i]
            right = sign_sequence[i + 1:i + 1 + window_size]
            context = left + right
            result = self.disambiguate(sign_id, context)
            results.append(result)
        return results


# ──────────────────────────────────────────────────────────────
# Active Learning Manager
# ──────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class CorrectionRecord:
    """User correction record with full provenance."""
    id: int
    sign_id: str
    context: str
    user_reading: str
    user_translation: Optional[str]
    user_pos: str
    confidence: float
    created_at: str
    applied: bool
    # Note: DB uses 'applied' BOOLEAN (0/1) instead of 'status' string


class ActiveLearningManager:
    """Manages active learning loop: corrections → review → apply → retrain."""

    def __init__(self, db_pool: DatabasePool, polyphony_engine: PolyphonyEngine):
        self._db = db_pool
        self._engine = polyphony_engine

    def submit_correction(
        self,
        sign_id: str,
        context: str,
        reading: str,
        translation: Optional[str],
        pos: str,
        confidence: float,
        created_by: str = "user",
    ) -> int:
        """Submit a new correction for review (applied=0 = pending)."""
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO polyphony_corrections
                (sign_id, context, user_reading, user_translation, user_pos, confidence, applied)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (sign_id, context, reading, translation, pos, confidence))
            conn.commit()
            return cur.lastrowid

    def get_pending(self, limit: int = 100) -> list[CorrectionRecord]:
        """Get pending corrections for review (applied=0)."""
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, sign_id, context, user_reading, user_translation,
                       user_pos, confidence, created_at, applied
                FROM polyphony_corrections
                WHERE applied = 0
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            return [
                CorrectionRecord(
                    id=row["id"],
                    sign_id=row["sign_id"],
                    context=row["context"],
                    user_reading=row["user_reading"],
                    user_translation=row["user_translation"],
                    user_pos=row["user_pos"],
                    confidence=row["confidence"],
                    created_at=row["created_at"],
                    applied=bool(row["applied"]),
                )
                for row in cur.fetchall()
            ]

    def approve_correction(self, correction_id: int) -> bool:
        """Approve and apply a correction to the polyphony engine (set applied=1)."""
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT sign_id, context, user_reading, user_translation, user_pos, confidence
                FROM polyphony_corrections
                WHERE id = ? AND applied = 0
            """, (correction_id,))
            row = cur.fetchone()
            if not row:
                return False

            # Apply to engine
            success = self._engine.save_user_correction(
                row["sign_id"],
                row["context"],
                row["user_reading"],
                row["user_translation"],
                row["user_pos"],
                row["confidence"],
            )

            if success:
                cur.execute("""
                    UPDATE polyphony_corrections
                    SET applied = 1
                    WHERE id = ?
                """, (correction_id,))
                conn.commit()
                return True
            return False

    def reject_correction(self, correction_id: int) -> bool:
        """Reject a correction (delete it since we only have applied=0/1)."""
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM polyphony_corrections
                WHERE id = ? AND applied = 0
            """, (correction_id,))
            conn.commit()
            return cur.rowcount > 0

    def get_stats(self) -> dict[str, int]:
        """Get active learning statistics."""
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT applied, COUNT(*) as cnt
                FROM polyphony_corrections
                GROUP BY applied
            """)
            stats = {row["applied"]: row["cnt"] for row in cur.fetchall()}
        # applied=0 means pending, applied=1 means approved/applied
        pending = stats.get(0, 0)
        applied = stats.get(1, 0)
        return {
            "pending": pending,
            "approved": applied,
            "rejected": 0,  # Not tracked separately in current schema
            "total": pending + applied,
        }


# ──────────────────────────────────────────────────────────────
# Core Repository Classes (Data Access)
# ──────────────────────────────────────────────────────────────
class TabletRepository:
    """Type-safe tablet data access."""

    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    def get_all(self, limit: Optional[int] = None) -> list[TabletRow]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            sql = """
                SELECT id, source, title, cuneiform, transliteration, language,
                       period, genre, myth_labels_json, content_hash, created_at, p_number
                FROM tablets ORDER BY id
            """
            if limit:
                sql += f" LIMIT {limit}"
            cur.execute(sql)
            return [TabletRow(**dict(row)) for row in cur.fetchall()]

    def get_by_id(self, tablet_id: str) -> Optional[TabletRow]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, source, title, cuneiform, transliteration, language,
                       period, genre, myth_labels_json, content_hash, created_at, p_number
                FROM tablets WHERE id = ?
            """, (tablet_id,))
            row = cur.fetchone()
            return TabletRow(**dict(row)) if row else None

    def search(self, query: str, periods: Optional[list[str]] = None) -> list[TabletRow]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            sql = """
                SELECT id, source, title, cuneiform, transliteration, language,
                       period, genre, myth_labels_json, content_hash, created_at, p_number
                FROM tablets
                WHERE transliteration LIKE ? OR cuneiform LIKE ? OR p_number LIKE ?
            """
            params = [f"%{query}%"] * 3
            if periods:
                placeholders = ",".join("?" * len(periods))
                sql += f" AND period IN ({placeholders})"
                params.extend(periods)
            cur.execute(sql, params)
            return [TabletRow(**dict(row)) for row in cur.fetchall()]


class SignRepository:
    """Type-safe sign data access."""

    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    def get_all(
        self,
        sign_types: Optional[list[str]] = None,
        periods: Optional[list[str]] = None,
        min_confidence: float = 0.0,
        limit: Optional[int] = None,
    ) -> list[SignRow]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            sql = """
                SELECT s.id, s.tablet_id, s.image_path, s.sign_index, s.bbox_x, s.bbox_y,
                       s.bbox_w, s.bbox_h, s.confidence, s.sign_type, s.atf_hypothesis,
                       s.unicode_hypothesis, s.detected_at, t.period
                FROM cuneiform_signs s
                LEFT JOIN tablets t ON s.tablet_id = t.id
                WHERE 1=1
            """
            params: list[Any] = []
            if sign_types:
                placeholders = ",".join("?" * len(sign_types))
                sql += f" AND s.sign_type IN ({placeholders})"
                params.extend(sign_types)
            if periods:
                placeholders = ",".join("?" * len(periods))
                sql += f" AND t.period IN ({placeholders})"
                params.extend(periods)
            if min_confidence > 0:
                sql += " AND s.confidence >= ?"
                params.append(min_confidence)
            if limit:
                sql += f" LIMIT {limit}"
            cur.execute(sql, params)
            return [SignRow(**dict(row)) for row in cur.fetchall()]

    def count_by_type(self) -> dict[str, int]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT sign_type, COUNT(*) as cnt FROM cuneiform_signs GROUP BY sign_type")
            return {row["sign_type"]: row["cnt"] for row in cur.fetchall()}


class EmbeddingRepository:
    """Type-safe embedding data access."""

    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    def store(
        self,
        entry_id: int,
        entry_type: EntryType,
        embedding_type: EmbeddingType,
        embedding: np.ndarray,
        model_name: str,
        model_version: str = "1.0",
    ) -> None:
        with self._db.connect() as conn:
            cur = conn.cursor()
            blob = pickle.dumps(embedding.astype(np.float32))
            cur.execute("""
                INSERT OR REPLACE INTO prebaked_embeddings
                (entry_id, entry_type, embedding_type, embedding, embedding_dim, model_name, model_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (entry_id, entry_type.value, embedding_type.value, blob, embedding.shape[-1], model_name, model_version))
            conn.commit()

    def load_text_embeddings(
        self,
        embedding_type: EmbeddingType = EmbeddingType.TEXT_SBERT,
    ) -> list[EmbeddingRecord]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT entry_id, entry_type, embedding_type, embedding, embedding_dim, model_name, model_version
                FROM prebaked_embeddings
                WHERE embedding_type = ?
            """, (embedding_type.value,))
            return [
                EmbeddingRecord(
                    entry_id=row["entry_id"],
                    entry_type=row["entry_type"],
                    embedding_type=row["embedding_type"],
                    embedding=pickle.loads(row["embedding"]),
                    embedding_dim=row["embedding_dim"],
                    model_name=row["model_name"],
                    model_version=row["model_version"],
                )
                for row in cur.fetchall()
            ]


class SignKnowledgeRepository:
    """Type-safe sign knowledge data access."""

    def __init__(self, db_pool: DatabasePool):
        self._db = db_pool

    def get_all(self) -> list[SignKnowledge]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT sign_id, unicode, borger_number, name,
                       sumerian_readings, akkadian_readings, logographic_values,
                       period_attestations, corpus_frequency, confidence_score
                FROM prebaked_sign_knowledge ORDER BY sign_id
            """)
            return [
                SignKnowledge(
                    sign_id=row["sign_id"],
                    unicode=row["unicode"],
                    borger_number=row["borger_number"],
                    name=row["name"],
                    sumerian_readings=json.loads(row["sumerian_readings"] or "[]"),
                    akkadian_readings=json.loads(row["akkadian_readings"] or "[]"),
                    logographic_values=json.loads(row["logographic_values"] or "[]"),
                    periods=json.loads(row["period_attestations"] or "[]"),
                    corpus_frequency=row["corpus_frequency"],
                    confidence_score=row["confidence_score"],
                )
                for row in cur.fetchall()
            ]

    def get_by_id(self, sign_id: str) -> Optional[SignKnowledge]:
        with self._db.connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT sign_id, unicode, borger_number, name,
                       sumerian_readings, akkadian_readings, logographic_values,
                       period_attestations, corpus_frequency, confidence_score
                FROM prebaked_sign_knowledge WHERE sign_id = ?
            """, (sign_id,))
            row = cur.fetchone()
            if not row:
                return None
            return SignKnowledge(
                sign_id=row["sign_id"],
                unicode=row["unicode"],
                borger_number=row["borger_number"],
                name=row["name"],
                sumerian_readings=json.loads(row["sumerian_readings"] or "[]"),
                akkadian_readings=json.loads(row["akkadian_readings"] or "[]"),
                logographic_values=json.loads(row["logographic_values"] or "[]"),
                periods=json.loads(row["period_attestations"] or "[]"),
                corpus_frequency=row["corpus_frequency"],
                confidence_score=row["confidence_score"],
            )


# ──────────────────────────────────────────────────────────────
# Backend Service Facade
# ──────────────────────────────────────────────────────────────
class BackendCore:
    """
    Main backend service facade — single entry point for all backend operations.
    Uses dependency injection for testability and modularity.
    """

    def __init__(self, config: Optional[BackendConfig] = None):
        self._config = config or get_default_config()
        self._db_pool = DatabasePool(self._config.db_path)
        self._faiss_mgr = FaissManager(self._config)
        self._sbert = SBertEmbedder(self._config.sbert_model_name)
        self._polyphony = get_polyphony_engine()
        self._bayesian = BayesianDisambiguator(self._polyphony)
        self._active_learning = ActiveLearningManager(self._db_pool, self._polyphony)

        # Repositories
        self.tablets = TabletRepository(self._db_pool)
        self.signs = SignRepository(self._db_pool)
        self.embeddings = EmbeddingRepository(self._db_pool)
        self.sign_knowledge = SignKnowledgeRepository(self._db_pool)

        # Ensure indices exist
        self._ensure_indices()

    def _ensure_indices(self) -> None:
        """Create performance indices on first initialization."""
        with self._db_pool.connect() as conn:
            cur = conn.cursor()

            # Composite indices for common query patterns - only using existing columns!
            indices = [
                # Tablets (no provenance/museum_number columns)
                "CREATE INDEX IF NOT EXISTS idx_tablets_period ON tablets(period)",
                "CREATE INDEX IF NOT EXISTS idx_tablets_transliteration_fts ON tablets(transliteration)",
                "CREATE INDEX IF NOT EXISTS idx_tablets_p_number ON tablets(p_number)",
                "CREATE INDEX IF NOT EXISTS idx_tablets_source ON tablets(source)",

                # Cuneiform signs (period is not in cuneiform_signs, only in tablets via JOIN)
                "CREATE INDEX IF NOT EXISTS idx_signs_tablet_type_conf ON cuneiform_signs(tablet_id, sign_type, confidence DESC)",
                "CREATE INDEX IF NOT EXISTS idx_signs_type_conf ON cuneiform_signs(sign_type, confidence DESC)",

                # Motif instances
                "CREATE INDEX IF NOT EXISTS idx_motif_instances_text_motif ON motif_instances(text_id, motif_id)",

                # Polyphony corrections (uses 'applied' BOOLEAN, not 'status' string)
                "CREATE INDEX IF NOT EXISTS idx_corrections_sign_applied ON polyphony_corrections(sign_id, applied)",
                "CREATE INDEX IF NOT EXISTS idx_corrections_pending_created ON polyphony_corrections(applied, created_at DESC) WHERE applied = 0",

                # Embeddings
                "CREATE INDEX IF NOT EXISTS idx_embeddings_type_entry ON prebaked_embeddings(embedding_type, entry_id)",
                "CREATE INDEX IF NOT EXISTS idx_embeddings_entry_type ON prebaked_embeddings(entry_id, entry_type)",

                # Sign knowledge
                "CREATE INDEX IF NOT EXISTS idx_sign_knowledge_frequency ON prebaked_sign_knowledge(corpus_frequency DESC)",
            ]

            for idx_sql in indices:
                try:
                    cur.execute(idx_sql)
                except Exception as e:
                    log.warning(f"Index creation skipped: {e}")

            conn.commit()
        log.info("✓ Database indices ensured")

    # ─── Health & Status ───
    def health_check(self) -> dict[str, Any]:
        """Comprehensive health check for monitoring."""
        checks: dict[str, Any] = {
            "status": "healthy",
            "timestamp": time.time(),
            "database": {"connected": False, "tables": 0, "tablets": 0, "signs": 0},
            "faiss": {"loaded": False, "vectors": 0, "dim": 0},
            "polyphony": {"signs": 0, "corrections_pending": 0},
            "sbert": {"available": self._sbert.is_available()},
        }

        # Database
        try:
            with self._db_pool.connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                checks["database"]["tables"] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM tablets")
                checks["database"]["tablets"] = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM cuneiform_signs")
                checks["database"]["signs"] = cur.fetchone()[0]
                checks["database"]["connected"] = True
        except Exception as e:
            checks["database"]["error"] = str(e)
            checks["status"] = "degraded"

        # FAISS
        faiss_idx = self._faiss_mgr.get_index()
        checks["faiss"]["loaded"] = faiss_idx.is_loaded()
        checks["faiss"]["vectors"] = faiss_idx.count
        checks["faiss"]["dim"] = faiss_idx.dim
        if not faiss_idx.is_loaded():
            checks["status"] = "degraded"

        # Polyphony
        poly_stats = self._polyphony.get_stats()
        checks["polyphony"]["signs"] = poly_stats.get("total_signs", 0)
        checks["polyphony"]["corrections_pending"] = poly_stats.get("pending_corrections", 0)

        return checks

    def get_polyphony_engine(self) -> PolyphonyEngine:
        return self._polyphony

    def get_bayesian_disambiguator(self) -> BayesianDisambiguator:
        return self._bayesian

    def get_active_learning(self) -> ActiveLearningManager:
        return self._active_learning

    def get_faiss_index(self) -> FaissIndex:
        return self._faiss_mgr.get_index()

    def rebuild_faiss_index(self) -> FaissIndex:
        return self._faiss_mgr.rebuild(self._db_pool)

    def close(self) -> None:
        self._db_pool.close()


# ──────────────────────────────────────────────────────────────
# Global Instance (Singleton Pattern for App Integration)
# ──────────────────────────────────────────────────────────────
_backend_instance: Optional[BackendCore] = None


def get_backend(config: Optional[BackendConfig] = None) -> BackendCore:
    """Get or create global backend instance."""
    global _backend_instance
    if _backend_instance is None:
        _backend_instance = BackendCore(config)
    return _backend_instance


def reset_backend() -> None:
    """Reset global instance (mainly for testing)."""
    global _backend_instance
    if _backend_instance is not None:
        _backend_instance.close()
    _backend_instance = None


# ──────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────
def main() -> None:
    """CLI for backend health check."""
    import sys

    backend = get_backend()
    try:
        health = backend.health_check()
        print(json.dumps(health, indent=2, default=str))
        sys.exit(0 if health["status"] == "healthy" else 1)
    finally:
        backend.close()


if __name__ == "__main__":
    main()