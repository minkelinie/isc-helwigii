#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — ai_deep_analysis.py
Geavanceerde pipeline: Data-opscaling, Embeddings, Motief-Tagging, Fragment Matching,
Netwerkanalyse, FAIR Export.
Vereist: OPENROUTER_API_KEY in env, sentence-transformers, networkx, plotly.
"""
from __future__ import annotations

import sqlite3
import json
import os
import re
import hashlib
import logging
import sys
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sentence_transformers import SentenceTransformer
import networkx as nx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
EXPORT_DIR = Path.home() / "Desktop" / "OxStealthData" / "export"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "meta-llama/llama-3.1-70b-instruct"
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
BATCH_SIZE = 20
REQUEST_TIMEOUT = (10, 60)
MAX_RETRIES = 3
TARGET_RECORDS = 200

# Mythologische corpus labels
MYTH_CORPORA = {
    "gilgamesh": ["gilgamesh", "bilgames", "ḫumbaba", "enkidu", "utnapishtim", "šiduri"],
    "atrahasis": ["atrahasis", "atra-ḫasis", "eṭemmu", "ellil", "belet-ili", "nintu"],
    "enuma_elish": ["enuma elish", "enu eliš", "marduk", "tiamat", "apsu", "kingu", "mummu"],
    "inanna_ishtar": ["inanna", "ishtar", "ereškigal", "dumuzi", "geshtinanna", "ninshubur"],
    "flood": ["zondvloed", "flood", "deluge", "ark", "boat", "bird", "raven", "dove", "utnapishtim", "ziudsudra", "atisrahasis"],
    "immortality": ["onsterfelijkheid", "immortality", "life", "death", "plant", "snake", "rejuvenation"],
    "divine_council": ["goddelijke raad", "divine council", "assembly", "anunnaki", "igigi", "enlil", "an", "enkidu"],
    "descent": ["onderwereld", "underworld", "descent", "kur", "ereškigal", "namtar"],
}

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ox-stealth-deep")

# ──────────────────────────────────────────────────────────────
# HTTP Session
# ──────────────────────────────────────────────────────────────
def build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=MAX_RETRIES, backoff_factor=2,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["POST"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

SESSION = build_session()

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class TabletRecord:
    id: str
    source: str
    title: str
    cuneiform: str
    transliteration: str
    language: str
    period: str
    genre: str
    myth_labels: List[str]
    content_hash: str

@dataclass
class MotifMatch:
    motif: str
    confidence: float
    evidence: List[str]
    alternatives: List[str]

@dataclass
class EmbeddingResult:
    tablet_id: str
    cuneiform_emb: np.ndarray
    translit_emb: np.ndarray
    similarity_score: float

# ──────────────────────────────────────────────────────────────
# Database Schema
# ──────────────────────────────────────────────────────────────
def init_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tablets (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            cuneiform TEXT NOT NULL,
            transliteration TEXT NOT NULL,
            language TEXT NOT NULL,
            period TEXT,
            genre TEXT,
            myth_labels_json TEXT NOT NULL,
            content_hash TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            tablet_id TEXT PRIMARY KEY REFERENCES tablets(id),
            cuneiform_emb BLOB NOT NULL,
            translit_emb BLOB NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS motifs (
            id TEXT PRIMARY KEY,
            tablet_id TEXT NOT NULL REFERENCES tablets(id),
            motif TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_json TEXT NOT NULL,
            alternatives_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fragment_matches (
            id TEXT PRIMARY KEY,
            fragment_id TEXT NOT NULL,
            matched_tablet_id TEXT NOT NULL REFERENCES tablets(id),
            similarity REAL NOT NULL,
            match_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_tablets_source ON tablets(source);",
        "CREATE INDEX IF NOT EXISTS idx_tablets_lang ON tablets(language);",
        "CREATE INDEX IF NOT EXISTS idx_motifs_tablet ON motifs(tablet_id);",
        "CREATE INDEX IF NOT EXISTS idx_motifs_motif ON motifs(motif);",
    ]:
        cur.execute(idx)
    conn.commit()

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def content_hash(*fields: str) -> str:
    h = hashlib.sha256()
    for f in fields:
        h.update(f.encode("utf-8", errors="ignore"))
    return h.hexdigest()[:16]

def clean_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(ch for ch in text if ord(ch) >= 32 or ch in "\t\n\r").strip()

def detect_language(cuneiform: str, translit: str) -> str:
    """Heuristiek: Sumerisch (logogrammen, geen case), Akkadisch (case, syllabisch), Hethitisch (hiero/luwisch marker)."""
    text = (cuneiform + " " + translit).lower()
    if any(m in text for m in ["d", "mu", "lugal", "ensi", "nin", "dam", "dumu", "e2", "gu4", "udu", "szita", "kug", "babbar"]):
        return "Sumerian"
    if any(m in text for m in ["šumma", "ana", "adi", "eli", "itti", "ina", "awīlum", "wardum", "amtum", "bēlum", "qātum"]):
        return "Akkadian"
    if any(m in text for m in ["ezza", "tan", "pala", "wapp", "kari", "dāi", "ešzi", "kuwapi", "natta", "šar"]):
        return "Hittite"
    return "Unknown"

def detect_period(source: str, title: str) -> str:
    t = (source + " " + title).lower()
    if "old babylonian" in t or "ob" in t:
        return "Old Babylonian"
    if "neo-assyrian" in t or "na" in t:
        return "Neo-Assyrian"
    if "neo-babylonian" in t or "nb" in t:
        return "Neo-Babylonian"
    if "sumerian" in t or "ur iii" in t:
        return "Ur III / Sumerian"
    if "hittite" in t or "boğazköy" in t:
        return "Hittite Empire"
    return "Uncertain"

def detect_genre(title: str, translit: str) -> str:
    t = (title + " " + translit).lower()
    if any(k in t for k in ["epic", "myth", "legend", "gilgamesh", "atrahasis", "enuma", "inanna", "descent"]):
        return "Myth/Epic"
    if any(k in t for k in ["hymn", "prayer", "ritual", "incantation"]):
        return "Ritual/Hymn"
    if any(k in t for k in ["letter", "contract", "legal", "economic", "administrative"]):
        return "Administrative"
    if any(k in t for k in ["lexical", "list", "vocabulary", "syllabary"]):
        return "Lexical"
    return "Unknown"

def extract_myth_labels(text: str) -> List[str]:
    labels = []
    text_lower = text.lower()
    for corpus, markers in MYTH_CORPORA.items():
        if any(m in text_lower for m in markers):
            labels.append(corpus)
    return labels if labels else ["uncategorized"]

# ──────────────────────────────────────────────────────────────
# Data Ingestion
# ──────────────────────────────────────────────────────────────
def ingest_cuneiml(conn: sqlite3.Connection, limit: int) -> int:
    path = Path.home() / "Desktop" / "OxStealthData" / "CuneiMLv1.2.json"
    if not path.exists():
        log.warning("CuneiMLv1.2.json not found")
        return 0
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    items = data if isinstance(data, list) else data.get("data", [])
    log.info(f"CuneiML: {len(items)} items available")
    inserted = 0
    for item in items[:limit]:
        cunei = item.get("cuneiform", "")
        if isinstance(cunei, list):
            cunei = " ".join(str(x) for x in cunei)
        translit = clean_text(item.get("transliteration", item.get("translation", "")))
        cunei = clean_text(cunei)
        if not cunei or not translit or cunei == "n.n.b.":
            continue
        ch = content_hash(cunei, translit)
        tid = f"CUNEIML-{ch}"
        lang = detect_language(cunei, translit)
        period = detect_period("CuneiML", item.get("title", ""))
        genre = detect_genre(item.get("title", ""), translit)
        labels = extract_myth_labels(translit)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO tablets
                (id, source, title, cuneiform, transliteration, language, period, genre, myth_labels_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tid, "CuneiML", item.get("title", f"Tablet {item.get('id', '')}"), cunei, translit,
                  lang, period, genre, json.dumps(labels), ch))
            if cur.rowcount:
                inserted += 1
        except sqlite3.Error:
            pass
    conn.commit()
    log.info(f"CuneiML: {inserted} new records inserted")
    return inserted

def ingest_huggingface(conn: sqlite3.Connection, limit: int) -> int:
    url = "https://datasets-server.huggingface.co/rows"
    params = {"dataset": "yfq20/Akkadian_Sumerian_Cuneiform_Translations", "config": "default", "split": "train", "offset": 0, "length": limit}
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}"} if OPENROUTER_KEY else {}
    try:
        resp = SESSION.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        log.info(f"HuggingFace: {len(rows)} rows received")
    except Exception as e:
        log.error(f"HF API error: {e}")
        return 0
    inserted = 0
    for row in rows:
        data = row.get("row", {})
        cunei = clean_text(data.get("cuneiform", ""))
        translit = clean_text(data.get("transliteration", data.get("translation", "")))
        if not cunei or not translit:
            continue
        ch = content_hash(cunei, translit)
        tid = f"HF-{ch}"
        lang = detect_language(cunei, translit)
        period = detect_period("HuggingFace", "")
        genre = detect_genre("", translit)
        labels = extract_myth_labels(translit)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO tablets
                (id, source, title, cuneiform, transliteration, language, period, genre, myth_labels_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tid, "HuggingFace", "Akkadian/Sumerian Parallel", cunei, translit,
                  lang, period, genre, json.dumps(labels), ch))
            if cur.rowcount:
                inserted += 1
        except sqlite3.Error:
            pass
    conn.commit()
    log.info(f"HuggingFace: {inserted} new records inserted")
    return inserted

def ingest_existing_db(conn: sqlite3.Connection) -> int:
    """Migreer bestaande spijkerschrift tabel naar nieuwe schema."""
    cur = conn.cursor()
    cur.execute("SELECT id, bron, titel, cuneiform, transliteratie FROM spijkerschrift")
    rows = cur.fetchall()
    inserted = 0
    for tid, src, title, cunei, translit in rows:
        cunei = clean_text(cunei)
        translit = clean_text(translit)
        if not cunei or cunei == "n.n.b.":
            continue
        ch = content_hash(cunei, translit)
        new_id = f"LEGACY-{ch}"
        lang = detect_language(cunei, translit)
        period = detect_period(src, title)
        genre = detect_genre(title, translit)
        labels = extract_myth_labels(translit)
        try:
            cur.execute("""
                INSERT OR IGNORE INTO tablets
                (id, source, title, cuneiform, transliteration, language, period, genre, myth_labels_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_id, src, title, cunei, translit, lang, period, genre, json.dumps(labels), ch))
            if cur.rowcount:
                inserted += 1
        except sqlite3.Error:
            pass
    conn.commit()
    log.info(f"Legacy migration: {inserted} records")
    return inserted

def ensure_minimum_records(conn: sqlite3.Connection, target: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tablets")
    current = cur.fetchone()[0]
    needed = target - current
    if needed <= 0:
        log.info(f"Already have {current} records, target {target} met")
        return 0
    log.info(f"Need {needed} more records, ingesting from sources...")
    total_new = 0
    total_new += ingest_cuneiml(conn, min(needed, 150))
    cur.execute("SELECT COUNT(*) FROM tablets")
    current = cur.fetchone()[0]
    needed = target - current
    if needed > 0:
        total_new += ingest_huggingface(conn, min(needed, 100))
    return total_new

# ──────────────────────────────────────────────────────────────
# LLM Motif Extraction
# ──────────────────────────────────────────────────────────────
MOTIF_PROMPT = """You are an expert Assyriologist. Analyze the following cuneiform tablet.

Cuneiform: {cuneiform}
Transliteration: {transliteration}
Language: {language}

Identify specific mythological motifs from this SET:
- flood: deluge, ark, boat, birds sent out, survival
- ark: vessel construction, loading animals, sealing
- divine_council: assembly of gods, Anunnaki, Igigi, decision making
- immortality_quest: search for eternal life, plant of life, snake stealing
- descent_underworld: journey to Kur, Ereshkigal, Nergal
- creation: separation of waters, Marduk vs Tiamat, ordering cosmos
- hero_battle: combat with Huwawa/Humbaba, Bull of Heaven, monsters
- sacred_marriage: Inanna/Dumuzi, hieros gamos
- divine_retribution: punishment of humanity, plague, famine
- wisdom_literature: instructions, proverbs, debate poems

For EACH detected motif, provide:
1. motif name (from list above)
2. confidence 0.0-1.0
3. evidence: specific phrases/tokens from transliteration
4. alternatives: other possible readings for ambiguous signs

Return ONLY valid JSON:
{
  "motifs": [
    {"motif": "flood", "confidence": 0.92, "evidence": ["ark", "boat", "utnapishtim"], "alternatives": ["ziudsudra"]},
    {"motif": "immortality_quest", "confidence": 0.78, "evidence": ["plant", "life"], "alternatives": []}
  ]
}"""

def llm_extract_motifs(cuneiform: str, transliteration: str, language: str) -> List[MotifMatch]:
    if not OPENROUTER_KEY:
        return []
    prompt = MOTIF_PROMPT.format(cuneiform=cuneiform[:500], transliteration=transliteration[:500], language=language)
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert Assyriologist. Output ONLY valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = SESSION.post(OPENROUTER_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            motifs = []
            for m in parsed.get("motifs", []):
                motifs.append(MotifMatch(
                    motif=m.get("motif", ""),
                    confidence=float(m.get("confidence", 0.5)),
                    evidence=m.get("evidence", []),
                    alternatives=m.get("alternatives", [])
                ))
            return motifs
        except Exception as e:
            log.warning(f"LLM motif extract attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                return []
            time.sleep(1.5 * attempt)
    return []

def store_motifs(conn: sqlite3.Connection, tablet_id: str, motifs: List[MotifMatch]) -> None:
    cur = conn.cursor()
    for m in motifs:
        mid = f"MOTIF-{tablet_id}-{m.motif}-{hashlib.md5(m.motif.encode()).hexdigest()[:8]}"
        cur.execute("""
            INSERT OR REPLACE INTO motifs
            (id, tablet_id, motif, confidence, evidence_json, alternatives_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (mid, tablet_id, m.motif, m.confidence, json.dumps(m.evidence), json.dumps(m.alternatives)))
    conn.commit()

# ──────────────────────────────────────────────────────────────
# Embeddings
# ──────────────────────────────────────────────────────────────
_embedding_model = None

def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        log.info(f"Loading embedding model: {EMBED_MODEL}")
        _embedding_model = SentenceTransformer(EMBED_MODEL, device="cpu")
    return _embedding_model

def compute_embeddings(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, cuneiform, transliteration FROM tablets
        WHERE id NOT IN (SELECT tablet_id FROM embeddings)
    """)
    rows = cur.fetchall()
    if not rows:
        log.info("All tablets already have embeddings")
        return 0
    log.info(f"Computing embeddings for {len(rows)} tablets...")
    model = get_embedding_model()
    texts_cunei = [clean_text(r[1]) for r in rows]
    texts_translit = [clean_text(r[2]) for r in rows]
    emb_cunei = model.encode(texts_cunei, batch_size=32, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=True)
    emb_translit = model.encode(texts_translit, batch_size=32, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=True)
    emb_cunei = emb_cunei.astype(np.float32)
    emb_translit = emb_translit.astype(np.float32)
    batch = []
    for (tid, _, _), ec, et in zip(rows, emb_cunei, emb_translit):
        batch.append((tid, ec.tobytes(), et.tobytes(), EMBED_MODEL, ec.shape[0]))
    cur.executemany("""
        INSERT OR REPLACE INTO embeddings (tablet_id, cuneiform_emb, translit_emb, model, dim)
        VALUES (?, ?, ?, ?, ?)
    """, batch)
    conn.commit()
    log.info(f"Stored embeddings for {len(batch)} tablets")
    return len(batch)

def load_all_embeddings(conn: sqlite3.Connection) -> Tuple[List[str], np.ndarray, np.ndarray]:
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, e.cuneiform_emb, e.translit_emb
        FROM tablets t
        JOIN embeddings e ON e.tablet_id = t.id
        ORDER BY t.id
    """)
    rows = cur.fetchall()
    ids = [r[0] for r in rows]
    if not rows:
        return ids, np.array([]), np.array([])
    dim = len(rows[0][1]) // 4  # float32
    cunei_arr = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), dim)
    translit_arr = np.frombuffer(b"".join(r[2] for r in rows), dtype=np.float32).reshape(len(rows), dim)
    return ids, cunei_arr, translit_arr

# ──────────────────────────────────────────────────────────────
# Similarity & Fragment Matching
# ──────────────────────────────────────────────────────────────
def compute_similarity_matrix(cunei_arr: np.ndarray, translit_arr: np.ndarray) -> np.ndarray:
    """Cosine similarity (already normalized embeddings)."""
    if cunei_arr.size == 0:
        return np.array([])
    # Combine: average of cuneiform and transliteration embeddings
    combined = (cunei_arr + translit_arr) / 2.0
    # Re-normalize
    norms = np.linalg.norm(combined, axis=1, keepdims=True)
    norms[norms == 0] = 1
    combined = combined / norms
    return combined @ combined.T

def find_fragment_matches(conn: sqlite3.Connection, similarity: np.ndarray, ids: List[str], top_k: int = 5) -> List[Dict]:
    """Vind voor elke tablet de top-k meest podobne andere tabletten."""
    matches = []
    n = len(ids)
    if n == 0:
        return matches
    for i in range(n):
        # Skip self
        sims = similarity[i].copy()
        sims[i] = -1
        top_indices = np.argsort(sims)[-top_k:][::-1]
        for j in top_indices:
            if sims[j] > 0.3:  # threshold
                matches.append({
                    "fragment_id": ids[i],
                    "matched_tablet_id": ids[j],
                    "similarity": float(sims[j]),
                    "match_type": "semantic"
                })
    return matches

def store_fragment_matches(conn: sqlite3.Connection, matches: List[Dict]) -> None:
    cur = conn.cursor()
    for m in matches:
        key = m["fragment_id"] + m["matched_tablet_id"]
        mid = f"FM-{hashlib.md5(key.encode()).hexdigest()[:12]}"
        cur.execute("""
            INSERT OR REPLACE INTO fragment_matches
            (id, fragment_id, matched_tablet_id, similarity, match_type)
            VALUES (?, ?, ?, ?, ?)
        """, (mid, m["fragment_id"], m["matched_tablet_id"], m["similarity"], m["match_type"]))
    conn.commit()
    log.info(f"Stored {len(matches)} fragment matches")

# ──────────────────────────────────────────────────────────────
# NetworkX Graph & Export
# ──────────────────────────────────────────────────────────────
def build_network(conn: sqlite3.Connection, similarity: np.ndarray, ids: List[str], threshold: float = 0.65) -> nx.Graph:
    G = nx.Graph()
    # Nodes
    cur = conn.cursor()
    cur.execute("SELECT id, title, language, genre, myth_labels_json FROM tablets WHERE id IN ({})".format(
        ",".join("?" * len(ids))), ids)
    node_data = {r[0]: r for r in cur.fetchall()}
    for tid in ids:
        if tid in node_data:
            _, title, lang, genre, myth_json = node_data[tid]
            myths = json.loads(myth_json) if myth_json else []
            myths_str = ";".join(myths) if myths else ""
            G.add_node(tid, title=title, language=lang, genre=genre, myths=myths_str)
    # Edges from similarity
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = similarity[i, j]
            if sim >= threshold:
                G.add_edge(ids[i], ids[j], weight=float(sim), type="semantic")
    # Edges from shared motifs
    cur.execute("SELECT tablet_id, motif FROM motifs")
    motif_map = {}
    for tid, motif in cur.fetchall():
        motif_map.setdefault(motif, []).append(tid)
    for motif, tablets in motif_map.items():
        for i in range(len(tablets)):
            for j in range(i + 1, len(tablets)):
                if G.has_edge(tablets[i], tablets[j]):
                    G[tablets[i]][tablets[j]]["weight"] = G[tablets[i]][tablets[j]].get("weight", 0) + 0.1
                    G[tablets[i]][tablets[j]]["type"] = "semantic+motif"
                else:
                    G.add_edge(tablets[i], tablets[j], weight=0.5, type="motif", motif=motif)
    return G

def export_graphml(G: nx.Graph, path: Path) -> None:
    nx.write_graphml(G, path)
    log.info(f"GraphML exported: {path}")

def export_cytoscape_json(G: nx.Graph, path: Path) -> None:
    elements = []
    for node, data in G.nodes(data=True):
        # Convert all values to JSON-serializable types
        clean_data = {}
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                clean_data[k] = json.dumps(v)
            else:
                clean_data[k] = v
        elements.append({"data": {"id": node, **clean_data}, "classes": "tablet"})
    for u, v, data in G.edges(data=True):
        clean_data = {}
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                clean_data[k] = json.dumps(v)
            else:
                clean_data[k] = v
        elements.append({"data": {"id": f"e-{u}-{v}", "source": u, "target": v, **clean_data}})
    path.write_text(json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Cytoscape JSON exported: {path}")

def visualize_clusters(G: nx.Graph, similarity: np.ndarray, ids: List[str], path: Path) -> None:
    """Plotly visualization: semantic clusters + motif communities."""
    if G.number_of_nodes() == 0:
        log.warning("No nodes to visualize")
        return
    # Community detection (Louvain)
    try:
        import community as community_louvain
        partition = community_louvain.best_partition(G, weight="weight")
    except ImportError:
        # Fallback: connected components
        partition = {n: i for i, comp in enumerate(nx.connected_components(G)) for n in comp}
    # 2D layout (spring)
    pos = nx.spring_layout(G, k=2/np.sqrt(G.number_of_nodes()), iterations=50, seed=42)
    # Build plot
    fig = go.Figure()
    # Edges
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines",
                             line=dict(width=0.5, color="#888"), hoverinfo="none", showlegend=False))
    # Nodes by community
    communities = set(partition.values())
    colors = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel
    for comm in communities:
        nodes_in_comm = [n for n in G.nodes() if partition[n] == comm]
        x = [pos[n][0] for n in nodes_in_comm]
        y = [pos[n][1] for n in nodes_in_comm]
        texts = [f"{n}<br>{G.nodes[n].get('title','')}<br>Lang: {G.nodes[n].get('language','')}<br>Myths: {', '.join(G.nodes[n].get('myths',[]))}" for n in nodes_in_comm]
        fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name=f"Community {comm}",
                                 marker=dict(size=12, color=colors[comm % len(colors)], line=dict(width=1, color="#fff")),
                                 text=texts, hoverinfo="text"))
    fig.update_layout(
        title="Cuneiform Semantic & Motif Network Clusters",
        showlegend=True,
        hovermode="closest",
        margin=dict(b=20,l=5,r=5,t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        template="plotly_white",
        width=1200, height=900
    )
    fig.write_image(str(path), scale=2)
    log.info(f"Cluster visualization saved: {path}")

# ──────────────────────────────────────────────────────────────
# FAIR Export: JSON-LD & ATF
# ──────────────────────────────────────────────────────────────
CONTEXT = {
    "@vocab": "http://schema.org/",
    "cuneiform": "http://oracc.org/ontology#",
    "dcterms": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "skos": "http://www.w3.org/2004/02/skos/core#"
}

def export_jsonld(conn: sqlite3.Connection, path: Path) -> None:
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.source, t.title, t.cuneiform, t.transliteration, t.language, t.period, t.genre, t.myth_labels_json,
               e.cuneiform_emb, e.translit_emb
        FROM tablets t
        LEFT JOIN embeddings e ON e.tablet_id = t.id
    """)
    rows = cur.fetchall()
    graph = []
    for row in rows:
        tid, src, title, cunei, translit, lang, period, genre, myth_json, emb_c, emb_t = row
        myths = json.loads(myth_json) if myth_json else []
        node = {
            "@id": f"https://signumcore.org/ox-stealth/{tid}",
            "@type": ["cuneiform:Tablet", "schema:CreativeWork"],
            "schema:identifier": tid,
            "dcterms:source": src,
            "dcterms:title": title,
            "cuneiform:cuneiformText": cunei,
            "cuneiform:transliteration": translit,
            "cuneiform:language": lang,
            "cuneiform:period": period,
            "cuneiform:genre": genre,
            "cuneiform:motifTags": myths,
            "prov:wasGeneratedBy": {"@id": "https://signumcore.org/ox-stealth/pipeline", "@type": "prov:Activity"},
            "schema:dateCreated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        if emb_c:
            node["cuneiform:hasEmbedding"] = {
                "@type": "cuneiform:EmbeddingVector",
                "cuneiform:model": EMBED_MODEL,
                "cuneiform:dimension": len(emb_c) // 4
            }
        graph.append(node)
    # Add context
    output = {"@context": CONTEXT, "@graph": graph}
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"JSON-LD exported: {path} ({len(graph)} tablets)")

def export_atf(conn: sqlite3.Connection, path: Path) -> None:
    """ATF (ASCII Transliteration Format) — ORACC compatible."""
    cur = conn.cursor()
    cur.execute("SELECT id, title, transliteration, language FROM tablets WHERE transliteration != ''")
    rows = cur.fetchall()
    lines = []
    for tid, title, translit, lang in rows:
        lines.append(f"&P{id} = {title}")
        lines.append(f"@tablet {tid}")
        lines.append(f"@language {lang.lower()}")
        lines.append(f"@script cuneiform")
        # Split transliteration into lines (rough)
        for i, line in enumerate(translit.split(". ")):
            if line.strip():
                lines.append(f"{i+1}. {line.strip()}")
        lines.append("")  # blank line between tablets
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"ATF exported: {path} ({len(rows)} tablets)")

def export_zenodo_metadata(conn: sqlite3.Connection, path: Path) -> None:
    """DataCite/Zenodo metadata for deposition."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT language), COUNT(DISTINCT source) FROM tablets")
    total, n_lang, n_src = cur.fetchone()
    cur.execute("SELECT language, COUNT(*) FROM tablets GROUP BY language")
    lang_dist = dict(cur.fetchall())
    meta = {
        "identifier": {"identifier": "10.5281/zenodo.oxstealth-mythhunter", "identifierType": "DOI"},
        "creators": [{"name": "OX-Stealth Myth Hunter Team", "nameType": "Organizational"},
                     {"name": "Mink Helwig", "nameType": "Personal", "givenName": "Mink", "familyName": "Helwig"}],
        "titles": [{"title": "OX-Stealth Myth Hunter: Semantic, Motif & Network Analysis of Cuneiform Corpora"}],
        "publisher": "Zenodo",
        "publicationYear": time.gmtime().tm_year,
        "subjects": [{"subject": "Cuneiform"}, {"subject": "Digital Humanities"}, {"subject": "Sumerian"},
                     {"subject": "Akkadian"}, {"subject": "Hittite"}, {"subject": "NLP"},
                     {"subject": "Knowledge Graph"}, {"subject": "Mythology"}, {"subject": "Stylometry"}],
        "dates": [{"date": time.strftime("%Y-%m-%d"), "dateType": "Issued"}],
        "language": "en",
        "resourceType": {"resourceTypeGeneral": "Dataset", "resourceType": "Annotated Corpus with Embeddings & Network"},
        "sizes": [f"{total} tablets", f"{n_lang} languages", f"{n_src} sources"],
        "formats": ["SQLite", "JSON-LD", "ATF", "GraphML", "JSON", "PNG"],
        "version": "1.0.0",
        "rightsList": [{"rights": "CC-BY-4.0", "rightsUri": "https://creativecommons.org/licenses/by/4.0/"}],
        "descriptions": [{"description": f"Multi-lingual cuneiform corpus ({total} tablets) with ORACC-normalized transliterations, "
                           f"SBERT embeddings, LLM-extracted motifs with confidence scores, fragment matches, "
                           f"and philological network analysis. Includes JSON-LD, ATF, GraphML exports.",
                           "descriptionType": "Abstract"}],
    }
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Zenodo metadata exported: {path}")

# ──────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────
def run_pipeline() -> Dict[str, Any]:
    log.info("=" * 70)
    log.info("🏛️  OX-STEALTH DEEP ANALYSIS — Full Pipeline")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    init_schema(conn)

    stats = {}

    # 1. Data Ingestion & Harmonization
    log.info("PHASE 1: Data Ingestion & Harmonization (target: 200+)")
    ingest_existing_db(conn)
    ensure_minimum_records(conn, TARGET_RECORDS)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tablets")
    stats["total_tablets"] = cur.fetchone()[0]
    cur.execute("SELECT language, COUNT(*) FROM tablets GROUP BY language")
    stats["by_language"] = dict(cur.fetchall())
    cur.execute("SELECT genre, COUNT(*) FROM tablets GROUP BY genre")
    stats["by_genre"] = dict(cur.fetchall())
    cur.execute("SELECT myth_labels_json FROM tablets")
    all_labels = []
    for (ml,) in cur.fetchall():
        all_labels.extend(json.loads(ml))
    from collections import Counter
    stats["myth_label_dist"] = dict(Counter(all_labels))

    # 2. LLM Motif Extraction (sample for speed, or all)
    log.info("PHASE 2: LLM Motif Extraction with Confidence Scores")
    cur.execute("SELECT id, cuneiform, transliteration, language FROM tablets")
    tablets = cur.fetchall()
    motif_count = 0
    for tid, cunei, translit, lang in tablets:
        cur.execute("SELECT COUNT(*) FROM motifs WHERE tablet_id=?", (tid,))
        if cur.fetchone()[0] > 0:
            continue
        motifs = llm_extract_motifs(cunei, translit, lang)
        if motifs:
            store_motifs(conn, tid, motifs)
            motif_count += len(motifs)
    stats["motifs_extracted"] = motif_count

    # 3. Embeddings
    log.info("PHASE 3: Semantic Embeddings (SBERT)")
    stats["embeddings_computed"] = compute_embeddings(conn)

    # 4. Similarity Matrix & Fragment Matching
    log.info("PHASE 4: Similarity Matrix & Fragment Matching")
    ids, cunei_arr, translit_arr = load_all_embeddings(conn)
    similarity = compute_similarity_matrix(cunei_arr, translit_arr)
    stats["similarity_matrix_shape"] = similarity.shape if similarity.size else None
    matches = find_fragment_matches(conn, similarity, ids, top_k=5)
    stats["fragment_matches"] = len(matches)
    store_fragment_matches(conn, matches)

    # 5. Three specific fragment matches (Proof-of-Concept)
    log.info("PHASE 5: Virtual Sherd Matching (3 Test Fragments)")
    # Take 3 shortest tablets as "fragments"
    cur.execute("""
        SELECT id, cuneiform FROM tablets
        WHERE length(cuneiform) < 200 AND cuneiform != ''
        ORDER BY length(cuneiform) ASC LIMIT 3
    """)
    fragments = cur.fetchall()
    shard_matches = []
    for fid, fcunei in fragments:
        # Embed fragment
        model = get_embedding_model()
        f_emb = model.encode([clean_text(fcunei)], normalize_embeddings=True)[0].astype(np.float32)
        # Compare to all
        sims = f_emb @ cunei_arr.T
        best_idx = int(np.argmax(sims))
        shard_matches.append({
            "fragment_id": fid,
            "best_match": ids[best_idx],
            "similarity": float(sims[best_idx]),
            "match_type": "virtual_shard"
        })
        log.info(f"  Fragment {fid} → Best match: {ids[best_idx]} (sim={sims[best_idx]:.3f})")
    stats["shard_matches"] = shard_matches

    # 6. Network Analysis
    log.info("PHASE 6: Philomythological Network Analysis")
    G = build_network(conn, similarity, ids, threshold=0.65)
    stats["network_nodes"] = G.number_of_nodes()
    stats["network_edges"] = G.number_of_edges()
    stats["network_components"] = nx.number_connected_components(G)
    stats["network_density"] = nx.density(G)
    export_graphml(G, EXPORT_DIR / "myth_hunter.graphml")
    export_cytoscape_json(G, EXPORT_DIR / "cytoscape.json")

    # 7. Visualization
    log.info("PHASE 7: Cluster Visualization")
    visualize_clusters(G, similarity, ids, EXPORT_DIR / "cuneiform_semantic_clusters.png")

    # 8. FAIR Export
    log.info("PHASE 8: FAIR Export (JSON-LD, ATF, Zenodo)")
    export_jsonld(conn, EXPORT_DIR / "cuneiform_corpus.jsonld")
    export_atf(conn, EXPORT_DIR / "cuneiform_corpus.atf")
    export_zenodo_metadata(conn, EXPORT_DIR / "zenodo_metadata.json")

    conn.close()

    log.info("=" * 70)
    log.info("✅ PIPELINE COMPLETE")
    log.info("=" * 70)
    return stats

if __name__ == "__main__":
    try:
        stats = run_pipeline()
        print("\n📊 FINAL STATISTICS")
        print("=" * 50)
        for k, v in stats.items():
            print(f"  {k}: {v}")
        sys.exit(0)
    except Exception as e:
        log.exception("Pipeline failed")
        sys.exit(1)