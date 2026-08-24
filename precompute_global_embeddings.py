#!/usr/bin/env python3
"""
PRE-COMPUTED GLOBAL EMBEDDINGS & FAISS INDEXER
Compute neural text embeddings + ORB visual features for all corpus entries.
Store in prebaked_embeddings/prebaked_sign_knowledge tables.
"""

import sqlite3
import json
import numpy as np
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import pickle
from tqdm import tqdm

# Optional FAISS - handle gracefully if not available
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("FAISS not available - will use numpy fallback")

# Optional sentence-transformers - handle gracefully
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available - using TF-IDF fallback")

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
log = logging.getLogger("embedding-precompute")

DB_PATH = Path("/data/cuneiform_master.db") if Path("/data/cuneiform_master.db").exists() else Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
PREBAKED_DIR = Path("/data/prebaked_embeddings")
PREBAKED_DIR.mkdir(parents=True, exist_ok=True)

# ———————————————————————————————————————————————————————————————
# Database Schema for Prebaked Tables
# ———————————————————————————————————————————————————————————————
PREBAKED_EMBEDDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS prebaked_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    entry_type TEXT NOT NULL,  -- 'tablet', 'myth_text', 'corpus_catalog'
    embedding_type TEXT NOT NULL,  -- 'text_sbert', 'text_tfidf_svd', 'visual_orb', 'visual_bovw'
    embedding BLOB NOT NULL,  -- Pickled numpy array
    embedding_dim INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entry_id) REFERENCES corpus_catalog(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prebaked_entry ON prebaked_embeddings(entry_id, entry_type, embedding_type);
"""

PREBAKED_SIGN_KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS prebaked_sign_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sign_id TEXT NOT NULL UNIQUE,  -- e.g., 'A', 'AN', 'LUGAL'
    unicode TEXT,
    borger_number TEXT,
    name TEXT,
    visual_features BLOB,  -- Pickled ORB/BoVW features
    text_embedding BLOB,  -- Pickled text embedding
    sumerian_readings TEXT,  -- JSON array
    akkadian_readings TEXT,  -- JSON array
    logographic_values TEXT,  -- JSON array
    period_attestations TEXT,  -- JSON array of periods
    corpus_frequency INTEGER DEFAULT 0,
    confidence_score REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sign_knowledge_id ON prebaked_sign_knowledge(sign_id);
"""

FAISS_INDEX_PATH = PREBAKED_DIR / "faiss_index.bin"
FAISS_META_PATH = PREBAKED_DIR / "faiss_metadata.json"

# ———————————————————————————————————————————————————————————————
# Text Embedding Models
# ———————————————————————————————————————————————————————————————
class TextEmbedder:
    """Multi-model text embedder with fallbacks."""

    def __init__(self):
        self.sbert_model = None
        self.tfidf_vectorizer = None
        self.svd = None
        self._init_models()

    def _init_models(self):
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                log.info("Loading SentenceTransformer model...")
                self.sbert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
                log.info("✓ SentenceTransformer loaded")
            except Exception as e:
                log.warning(f"Failed to load SentenceTransformer: {e}")
                self.sbert_model = None

        # TF-IDF + SVD fallback
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            sublinear_tf=True,
            min_df=1
        )
        self.svd = TruncatedSVD(n_components=384, random_state=42)  # Match SBERT dim

    def embed_texts_sbert(self, texts: List[str]) -> np.ndarray:
        """Embed texts using SentenceTransformer."""
        if self.sbert_model is None:
            return np.array([])
        embeddings = self.sbert_model.encode(texts, show_progress_bar=True, batch_size=32)
        return embeddings.astype(np.float32)

    def embed_texts_tfidf_svd(self, texts: List[str]) -> np.ndarray:
        """Embed texts using TF-IDF + SVD."""
        tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
        svd_embeddings = self.svd.fit_transform(tfidf_matrix)
        return svd_embeddings.astype(np.float32)

    def embed_texts(self, texts: List[str], prefer_sbert: bool = True) -> Tuple[np.ndarray, str]:
        """Embed texts with best available model."""
        if prefer_sbert and SENTENCE_TRANSFORMERS_AVAILABLE and self.sbert_model is not None:
            return self.embed_texts_sbert(texts), "sbert"
        else:
            return self.embed_texts_tfidf_svd(texts), "tfidf_svd"


class VisualFeatureExtractor:
    """Extract ORB and BoVW visual features from tablet images."""

    def __init__(self):
        self.orb = None
        self.bovw_vocabulary = None
        if OPENCV_AVAILABLE:
            self.orb = cv2.ORB_create(nfeatures=500, scaleFactor=1.2, nlevels=8)

    def extract_orb(self, image_path: Path) -> Optional[np.ndarray]:
        """Extract ORB descriptors from image."""
        if not OPENCV_AVAILABLE or self.orb is None:
            return None
        if not image_path.exists():
            return None

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None

        kp, des = self.orb.detectAndCompute(img, None)
        if des is not None:
            return des.astype(np.float32)
        return None

    def build_bovw_vocabulary(self, all_descriptors: List[np.ndarray], n_clusters: int = 256) -> np.ndarray:
        """Build Bag-of-Visual-Words vocabulary using k-means on ORB descriptors."""
        if not OPENCV_AVAILABLE:
            return np.random.rand(n_clusters, 32).astype(np.float32)  # ORB descriptors are 32-dim

        # Stack all descriptors
        stacked = np.vstack([d for d in all_descriptors if d is not None and len(d) > 0])
        if len(stacked) < n_clusters:
            return np.random.rand(n_clusters, 32).astype(np.float32)

        # K-means clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.1)
        _, labels, centers = cv2.kmeans(
            stacked.astype(np.float32),
            n_clusters,
            None,
            criteria,
            10,
            cv2.KMEANS_PP_CENTERS
        )
        self.bovw_vocabulary = centers.astype(np.float32)
        return self.bovw_vocabulary

    def compute_bovw_histogram(self, descriptors: np.ndarray) -> np.ndarray:
        """Compute BoVW histogram for descriptors."""
        if self.bovw_vocabulary is None or descriptors is None or len(descriptors) == 0:
            return np.zeros(256, dtype=np.float32)

        # Assign each descriptor to nearest vocabulary word
        distances = np.linalg.norm(descriptors[:, np.newaxis] - self.bovw_vocabulary, axis=2)
        assignments = np.argmin(distances, axis=1)
        histogram = np.bincount(assignments, minlength=len(self.bovw_vocabulary))
        return (histogram / histogram.sum()).astype(np.float32) if histogram.sum() > 0 else np.zeros(256, dtype=np.float32)


# ———————————————————————————————————————————————————————————————
# Main Precomputation Pipeline
# ———————————————————————————————————————————————————————————————
def init_prebaked_tables(conn: sqlite3.Connection):
    """Create prebaked tables if they don't exist."""
    cur = conn.cursor()
    cur.executescript(PREBAKED_EMBEDDINGS_SCHEMA)
    cur.executescript(PREBAKED_SIGN_KNOWLEDGE_SCHEMA)
    conn.commit()
    log.info("✓ Prebaked tables initialized")


def store_embedding(conn: sqlite3.Connection, entry_id: int, entry_type: str,
                    embedding_type: str, embedding: np.ndarray,
                    model_name: str, model_version: str = "1.0"):
    """Store pickled embedding in database."""
    cur = conn.cursor()
    blob = pickle.dumps(embedding)
    cur.execute("""
        INSERT OR REPLACE INTO prebaked_embeddings
        (entry_id, entry_type, embedding_type, embedding, embedding_dim, model_name, model_version)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (entry_id, entry_type, embedding_type, blob, embedding.shape[-1], model_name, model_version))
    conn.commit()


def load_all_corpus_texts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Load all texts from all corpus sources for embedding."""
    cur = conn.cursor()
    texts = []

    # Tablets - use cuneiform column instead of translation
    cur.execute("""
        SELECT id as entry_id, 'tablet' as entry_type, transliteration, cuneiform as translation, p_number, source, period
        FROM tablets WHERE transliteration IS NOT NULL AND transliteration != ''
    """)
    for row in cur.fetchall():
        text_content = f"{row['transliteration']} {row['translation'] or ''}".strip()
        texts.append({
            'entry_id': row['entry_id'],
            'entry_type': 'tablet',
            'text': text_content,
            'metadata': dict(row)
        })

    # Myth texts
    cur.execute("""
        SELECT id as entry_id, 'myth_text' as entry_type, transliteration, translation, title, corpus_source, period
        FROM myth_texts WHERE transliteration IS NOT NULL AND transliteration != ''
    """)
    for row in cur.fetchall():
        text_content = f"{row['transliteration']} {row['translation'] or ''} {row['title'] or ''}".strip()
        texts.append({
            'entry_id': row['entry_id'],
            'entry_type': 'myth_text',
            'text': text_content,
            'metadata': dict(row)
        })

    # Corpus catalog
    cur.execute("""
        SELECT id as entry_id, 'corpus_catalog' as entry_type, transliteration, translation, title, source_corpus, period
        FROM corpus_catalog WHERE transliteration IS NOT NULL AND transliteration != ''
    """)
    for row in cur.fetchall():
        text_content = f"{row['transliteration']} {row['translation'] or ''} {row['title'] or ''}".strip()
        texts.append({
            'entry_id': row['entry_id'],
            'entry_type': 'corpus_catalog',
            'text': text_content,
            'metadata': dict(row)
        })

    return texts


def load_all_tablet_images(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Load all tablet image paths for visual feature extraction."""
    cur = conn.cursor()
    images = []

    # Check if tablets table has image_path column
    cur.execute("PRAGMA table_info(tablets)")
    columns = [row[1] for row in cur.fetchall()]

    if 'image_path' in columns:
        cur.execute("SELECT id, p_number, source, image_path FROM tablets WHERE image_path IS NOT NULL AND image_path != ''")
        for row in cur.fetchall():
            images.append({
                'entry_id': row['id'],
                'entry_type': 'tablet',
                'image_path': Path(row['image_path']),
                'metadata': dict(row)
            })

    # Try user_fragments for user-uploaded images (check table exists first)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_fragments'")
    if cur.fetchone():
        cur.execute("SELECT id, dataset_name, image_path FROM user_fragments WHERE image_path IS NOT NULL AND image_path != ''")
        for row in cur.fetchall():
            images.append({
                'entry_id': row['id'],
                'entry_type': 'user_fragment',
                'image_path': Path(row['image_path']),
                'metadata': dict(row)
            })

    # Also check images directory for any tablet images
    images_dir = Path("/data/images") if Path("/data/images").exists() else Path.home() / "Desktop" / "OxStealthData" / "images"
    if images_dir.exists():
        for img_file in images_dir.glob("*.jpg"):
            images.append({
                'entry_id': hash(img_file.stem) % 1000000,
                'entry_type': 'tablet_image',
                'image_path': img_file,
                'metadata': {'filename': img_file.name}
            })
        for img_file in images_dir.glob("*.png"):
            images.append({
                'entry_id': hash(img_file.stem) % 1000000,
                'entry_type': 'tablet_image',
                'image_path': img_file,
                'metadata': {'filename': img_file.name}
            })
        for img_file in images_dir.glob("*.tif"):
            images.append({
                'entry_id': hash(img_file.stem) % 1000000,
                'entry_type': 'tablet_image',
                'image_path': img_file,
                'metadata': {'filename': img_file.name}
            })
        for img_file in images_dir.glob("*.tiff"):
            images.append({
                'entry_id': hash(img_file.stem) % 1000000,
                'entry_type': 'tablet_image',
                'image_path': img_file,
                'metadata': {'filename': img_file.name}
            })

    return images


def compute_and_store_text_embeddings(conn: sqlite3.Connection):
    """Compute and store text embeddings for all corpus entries."""
    log.info("🔤 Computing text embeddings...")

    texts_data = load_all_corpus_texts(conn)
    if not texts_data:
        log.warning("No texts found in corpus")
        return

    log.info(f"  Found {len(texts_data)} texts to embed")

    embedder = TextEmbedder()

    # Prepare all texts
    all_texts = [item['text'] for item in texts_data]

    # Embed with best available model
    embeddings, model_used = embedder.embed_texts(all_texts)
    model_name = f"{model_used}-multilingual"
    log.info(f"  Using {model_name} (dim={embeddings.shape[1]})")

    # Store embeddings
    for i, item in enumerate(tqdm(texts_data, desc="Storing text embeddings")):
        store_embedding(
            conn,
            item['entry_id'],
            item['entry_type'],
            f"text_{model_used}",
            embeddings[i:i+1],
            model_name
        )

    log.info(f"✓ Stored {len(texts_data)} text embeddings")


def compute_and_store_visual_embeddings(conn: sqlite3.Connection):
    """Compute and store visual features for all tablet images."""
    if not OPENCV_AVAILABLE:
        log.warning("OpenCV not available - skipping visual embeddings")
        return

    log.info("👁️ Computing visual embeddings...")

    images = load_all_tablet_images(conn)
    if not images:
        log.warning("No tablet images found")
        return

    log.info(f"  Found {len(images)} images to process")

    extractor = VisualFeatureExtractor()

    # First pass: collect all ORB descriptors for BoVW vocabulary
    all_descriptors = []
    orb_results = {}

    for item in tqdm(images, desc="Extracting ORB descriptors"):
        des = extractor.extract_orb(item['image_path'])
        if des is not None:
            all_descriptors.append(des)
            orb_results[item['entry_id']] = des

    # Build BoVW vocabulary
    if all_descriptors:
        log.info("  Building BoVW vocabulary...")
        extractor.build_bovw_vocabulary(all_descriptors, n_clusters=256)

    # Second pass: compute BoVW histograms and store
    for item in tqdm(images, desc="Computing BoVW histograms"):
        entry_id = item['entry_id']
        orb_des = orb_results.get(entry_id)

        if orb_des is not None:
            # Store ORB descriptors
            store_embedding(
                conn, entry_id, item['entry_type'],
                'visual_orb', orb_des, 'ORB-v1'
            )

            # Compute and store BoVW histogram
            bovw_hist = extractor.compute_bovw_histogram(orb_des)
            store_embedding(
                conn, entry_id, item['entry_type'],
                'visual_bovw', bovw_hist.reshape(1, -1), 'BoVW-v1'
            )

    log.info(f"✓ Stored visual embeddings for {len(orb_results)} images")


def populate_sign_knowledge(conn: sqlite3.Connection, polyphony_path: Path):
    """Populate prebaked_sign_knowledge from polyphony catalog."""
    log.info("🔧 Populating sign knowledge base...")

    # Load polyphony catalog
    if polyphony_path.exists():
        with open(polyphony_path, 'r', encoding='utf-8') as f:
            polyphony = json.load(f)
    else:
        log.warning(f"Polyphony catalog not found at {polyphony_path}")
        return

    cur = conn.cursor()

    for sign_id, sign_data in polyphony.get('signs', {}).items():
        cur.execute("""
            INSERT OR REPLACE INTO prebaked_sign_knowledge
            (sign_id, unicode, borger_number, name,
             sumerian_readings, akkadian_readings, logographic_values,
             corpus_frequency, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sign_id,
            sign_data.get('unicode', ''),
            sign_data.get('borger', ''),
            sign_data.get('name', sign_id),
            json.dumps(sign_data.get('sumerian_readings', [])),
            json.dumps(sign_data.get('akkadian_readings', [])),
            json.dumps(sign_data.get('logographic_values', [])),
            sign_data.get('corpus_frequency', 0),
            1.0 if sign_data.get('observed_in_corpus', False) else 0.5
        ))

    conn.commit()
    log.info(f"✓ Populated {len(polyphony.get('signs', {}))} sign knowledge entries")


def build_faiss_index(conn: sqlite3.Connection):
    """Build FAISS index from all text embeddings for fast similarity search."""
    if not FAISS_AVAILABLE:
        log.warning("FAISS not available - skipping index build")
        return

    log.info("🔍 Building FAISS index...")

    cur = conn.cursor()
    cur.execute("""
        SELECT entry_id, entry_type, embedding, embedding_type
        FROM prebaked_embeddings
        WHERE embedding_type LIKE 'text_%'
    """)

    embeddings_data = cur.fetchall()
    if not embeddings_data:
        log.warning("No text embeddings found for FAISS index")
        return

    # Group by embedding type (use first type found)
    embedding_type = embeddings_data[0][3]
    entries = [(row[0], row[1], pickle.loads(row[2])) for row in embeddings_data if row[3] == embedding_type]

    if not entries:
        return

    # Stack embeddings
    vectors = np.vstack([e[2].flatten() for e in entries])

    # Create integer ID mapping for FAISS (requires int64 IDs)
    original_ids = [e[0] for e in entries]
    types = [e[1] for e in entries]

    # Map string IDs to sequential integers
    unique_ids = list(dict.fromkeys(original_ids))  # preserve order
    id_to_int = {orig_id: idx for idx, orig_id in enumerate(unique_ids)}
    int_ids = np.array([id_to_int[orig_id] for orig_id in original_ids], dtype=np.int64)

    log.info(f"  Indexing {len(vectors)} vectors (dim={vectors.shape[1]})")

    # Build FAISS index (IndexFlatIP for cosine similarity with normalized vectors)
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index = faiss.IndexIDMap(index)
    index.add_with_ids(vectors, int_ids)

    # Save index and metadata
    faiss.write_index(index, str(FAISS_INDEX_PATH))

    metadata = {
        'entry_ids': original_ids,
        'int_id_mapping': id_to_int,
        'entry_types': types,
        'embedding_type': embedding_type,
        'dim': vectors.shape[1],
        'count': len(int_ids)
    }
    with open(FAISS_META_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)

    log.info(f"✓ FAISS index saved to {FAISS_INDEX_PATH}")


def main():
    log.info("=" * 70)
    log.info("🧠 PRE-COMPUTED GLOBAL EMBEDDINGS & FAISS INDEXER")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        init_prebaked_tables(conn)

        # Text embeddings
        compute_and_store_text_embeddings(conn)

        # Visual embeddings
        compute_and_store_visual_embeddings(conn)

        # Sign knowledge from polyphony catalog
        polyphony_path = Path("/data/cuneiform_polyphony.json") if Path("/data/cuneiform_polyphony.json").exists() else Path.home() / "Desktop" / "OxStealthData" / "cuneiform_polyphony.json"
        populate_sign_knowledge(conn, polyphony_path)

        # FAISS index
        build_faiss_index(conn)

        log.info("=" * 70)
        log.info("✅ PRECOMPUTATION COMPLETE")
        log.info("=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    main()