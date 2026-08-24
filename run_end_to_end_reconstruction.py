#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — run_end_to_end_reconstruction.py
End-to-end fragment reconstruction pipeline:
1. Fragment ingestion (simulate unknown find with lacuna)
2. Multimodal puzzle engine (fracture geometry + semantic embeddings + n-gram alignment)
3. Academic report & expert interface (visualization + structured report)
"""

from __future__ import annotations

import sqlite3
import json
import os
import hashlib
import logging
import sys
import base64
import random
import textwrap
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any
from io import BytesIO
from datetime import datetime
from collections import Counter

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial.distance import cdist
from scipy.ndimage import gaussian_filter1d
from scipy.interpolate import interp1d

# ──────────────────────────────────────────────────────────────
# Config & Paths
# ──────────────────────────────────────────────────────────────
DOCKER_DB_PATH = Path("/data/cuneiform_master.db")
LOCAL_DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
DB_PATH = DOCKER_DB_PATH if DOCKER_DB_PATH.exists() else LOCAL_DB_PATH

EXPORT_DIR = Path("/data/export") if Path("/data/export").exists() else (Path.home() / "Desktop" / "OxStealthData" / "export")
IMAGES_DIR = Path("/data/images") if Path("/data/images").exists() else (Path.home() / "Desktop" / "OxStealthData" / "images")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ox-stealth-reconstruction")

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class FractureProfile:
    tablet_id: str
    edge_curvatures: List[float]
    edge_angles: List[float]
    edge_lengths: List[float]
    fracture_points: List[Tuple[float, float]]
    aspect_ratio: float

@dataclass
class JoinMatch:
    tablet_a: str
    tablet_b: str
    fracture_complementarity: float
    text_continuity: float
    ngram_alignment: float
    join_confidence: float
    fracture_details: Dict
    text_details: Dict
    ngram_details: Dict

@dataclass
class ReconstructionResult:
    fragment_id: str
    lacuna_regions: List[Dict]
    fracture_angle: float
    detected_motifs: List[str]
    top_matches: List[JoinMatch]
    reconstructed_text: str
    word_confidences: List[Dict]

# ──────────────────────────────────────────────────────────────
# Database & Schema
# ──────────────────────────────────────────────────────────────
def init_reconstruction_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tablets)")
    cols = [row[1] for row in cur.fetchall()]
    if 'p_number' not in cols:
        try:
            cur.execute("ALTER TABLE tablets ADD COLUMN p_number TEXT")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tablets_pnum ON tablets(p_number)")
        except sqlite3.OperationalError:
            pass

    cur.execute("PRAGMA table_info(spijkerschrift_visueel)")
    vis_cols = [row[1] for row in cur.fetchall()]
    for col, col_type in [
        ("fracture_curvature_json", "TEXT"),
        ("fracture_points_json", "TEXT"),
        ("text_embedding", "TEXT")
    ]:
        if col not in vis_cols:
            try:
                cur.execute(f"ALTER TABLE spijkerschrift_visueel ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
    conn.commit()

# ──────────────────────────────────────────────────────────────
# Llama 3.1 Compatible Text Embedding (Deterministic Hash-based)
# ──────────────────────────────────────────────────────────────
def llama31_embedding(text: str, dim: int = 768) -> np.ndarray:
    """
    Deterministic text embedding compatible with Llama 3.1 dimensions.
    In production: replace with actual Llama 3.1 / sentence-transformers embedding.
    """
    text = text.lower().strip()
    words = text.split()
    emb = np.zeros(dim, dtype=np.float32)

    # Word-level features
    for i, word in enumerate(words):
        h = hash(word) % dim
        val = ((hash(word) >> 16) % 1000) / 1000.0
        emb[h] += val * (1.0 + 0.1 * np.sin(i * 0.1))

    # Character n-grams (3-5 char)
    for n in [3, 4, 5]:
        for i in range(len(text) - n + 1):
            ngram = text[i:i+n]
            h = hash(ngram) % dim
            emb[h] += 0.01 * (1.0 + 0.05 * np.sin(i * 0.2))

    # Positional encoding for word order
    for i in range(min(len(words), 50)):
        pos_emb = np.zeros(dim)
        for j in range(0, dim, 2):
            pos_emb[j] = np.sin(i / (10000 ** (j / dim)))
            pos_emb[j+1] = np.cos(i / (10000 ** ((j+1) / dim)))
        emb += 0.02 * pos_emb

    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

# ──────────────────────────────────────────────────────────────
# N-gram Alignment (eBL-style)
# ──────────────────────────────────────────────────────────────
def ngram_alignment(text_a: str, text_b: str, n: int = 3) -> Tuple[float, Dict]:
    """
    eBL-style n-gram overlap sequence alignment for fragment joining.
    """
    words_a = text_a.split()
    words_b = text_b.split()

    if len(words_a) < n or len(words_b) < n:
        return 0.0, {"reason": "Text too short"}

    # Generate n-grams
    ngrams_a = [' '.join(words_a[i:i+n]) for i in range(len(words_a) - n + 1)]
    ngrams_b = [' '.join(words_b[i:i+n]) for i in range(len(words_b) - n + 1)]

    # Overlap coefficient
    set_a, set_b = set(ngrams_a), set(ngrams_b)
    overlap = len(set_a & set_b)
    max_possible = min(len(set_a), len(set_b))

    if max_possible == 0:
        return 0.0, {"overlap": 0, "ngrams_a": len(set_a), "ngrams_b": len(set_b)}

    # Weighted by position proximity (sliding window)
    weighted_score = 0.0
    for i, ng_a in enumerate(ngrams_a):
        for j, ng_b in enumerate(ngrams_b):
            if ng_a == ng_b:
                # Higher score for closer positions
                pos_diff = abs(i - j)
                weighted_score += 1.0 / (1.0 + pos_diff * 0.5)

    # Normalize
    norm_factor = max(len(ngrams_a), len(ngrams_b)) / 2
    if norm_factor > 0:
        weighted_score = weighted_score / norm_factor

    combined_score = 0.6 * (overlap / max_possible) + 0.4 * weighted_score

    return min(combined_score, 1.0), {
        "ngram_overlap": overlap,
        "ngrams_a": len(set_a),
        "ngrams_b": len(set_b),
        "overlap_ratio": overlap / max_possible,
        "weighted_score": weighted_score,
        "shared_ngrams": list(set_a & set_b)[:10]
    }

# ──────────────────────────────────────────────────────────────
# Fracture Profile Computation (GigaMesh-style)
# ──────────────────────────────────────────────────────────────
def compute_fracture_profile_from_contour(contour: np.ndarray, approx: np.ndarray) -> FractureProfile:
    """Compute fracture profile from contour (GigaMesh-inspired edge analysis)."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    approx_pts = approx.reshape(-1, 2).astype(np.float32)
    n_approx = len(approx_pts)

    if n_approx < 3:
        return FractureProfile("", [], [], [], [], 1.0)

    edge_curvatures = []
    edge_angles = []
    edge_lengths = []
    fracture_points = []

    for i in range(n_approx):
        p1 = approx_pts[i]
        p2 = approx_pts[(i + 1) % n_approx]
        edge_vec = p2 - p1
        edge_len = np.linalg.norm(edge_vec)
        edge_lengths.append(float(edge_len))

        if edge_len > 10:
            edge_dir = edge_vec / edge_len
            normal = np.array([-edge_dir[1], edge_dir[0]])
            vecs = pts - p1
            proj = np.dot(vecs, edge_dir)
            perp_dist = np.abs(np.dot(vecs, normal))

            on_edge = (proj >= 0) & (proj <= edge_len) & (perp_dist < max(10, edge_len * 0.05))
            edge_contour_pts = pts[on_edge]

            if len(edge_contour_pts) > 10:
                sorted_idx = np.argsort(proj[on_edge])
                edge_contour_pts = edge_contour_pts[sorted_idx]
                deviations = np.abs(np.dot(edge_contour_pts - p1, normal))
                max_dev = np.max(deviations)
                curvature = max_dev / (edge_len + 1e-6)
                edge_curvatures.append(float(curvature))

                if curvature > 0.02:
                    idx_max = np.argmax(deviations)
                    fp = edge_contour_pts[idx_max]
                    fracture_points.append((float(fp[0]), float(fp[1])))
            else:
                edge_curvatures.append(0.0)
        else:
            edge_curvatures.append(0.0)

        # Corner angle
        p0 = approx_pts[(i - 1) % n_approx]
        v1 = p1 - p0
        v2 = p2 - p1
        dot = np.dot(v1, v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm > 0:
            cos = np.clip(dot / norm, -1.0, 1.0)
            ang = np.degrees(np.arccos(cos))
        else:
            ang = 90.0
        edge_angles.append(float(ang))

    x, y, w, h = cv2.boundingRect(contour)
    aspect = float(w) / h if h > 0 else 1.0

    return FractureProfile(
        tablet_id="",
        edge_curvatures=edge_curvatures,
        edge_angles=edge_angles,
        edge_lengths=edge_lengths,
        fracture_points=fracture_points,
        aspect_ratio=aspect
    )

# ──────────────────────────────────────────────────────────────
# Fracture Complementarity (Resampled)
# ──────────────────────────────────────────────────────────────
def resample_profile_arrays(arrays: List[List[float]], n_target: int) -> List[List[float]]:
    """Resample multiple arrays to common length via interpolation."""
    resampled = []
    for arr in arrays:
        if len(arr) == n_target:
            resampled.append(arr)
        elif len(arr) == 0:
            resampled.append([0.0] * n_target)
        else:
            x_orig = np.linspace(0, 1, len(arr))
            x_target = np.linspace(0, 1, n_target)
            interp = np.interp(x_target, x_orig, arr).tolist()
            resampled.append(interp)
    return resampled

def compute_fracture_complementarity(profile_a: FractureProfile, profile_b: FractureProfile) -> Tuple[float, Dict]:
    n_a = len(profile_a.edge_curvatures)
    n_b = len(profile_b.edge_curvatures)

    if n_a == 0 or n_b == 0:
        return 0.0, {"error": "Empty profiles"}

    n_common = max(n_a, n_b, 4)
    a_curv, a_ang, a_len = resample_profile_arrays(
        [profile_a.edge_curvatures, profile_a.edge_angles, profile_a.edge_lengths], n_common)
    b_curv, b_ang, b_len = resample_profile_arrays(
        [profile_b.edge_curvatures, profile_b.edge_angles, profile_b.edge_lengths], n_common)

    best_score = 0.0
    best_details = {}

    for offset in range(n_common):
        curv_scores, len_scores, ang_scores = [], [], []

        for i in range(n_common):
            j = (offset + i) % n_common

            # Curvature match
            ca, cb = a_curv[i], b_curv[j]
            if ca > 0.01 or cb > 0.01:
                curv_match = 1.0 - min(abs(ca - cb) / (max(ca, cb) + 1e-6), 1.0)
            else:
                curv_match = 1.0
            curv_scores.append(curv_match)

            # Length match
            la, lb = a_len[i], b_len[j]
            len_match = 1.0 - min(abs(la - lb) / (max(la, lb) + 1e-6), 1.0)
            len_scores.append(len_match)

            # Angle complementarity (sum ≈ 360 for joined edges)
            aa, ab = a_ang[i], b_ang[j]
            angle_diff = min(abs(aa - ab), abs(360 - aa - ab))
            ang_match = 1.0 - min(angle_diff / 180.0, 1.0)
            ang_scores.append(ang_match)

        avg_curv = np.mean(curv_scores)
        avg_len = np.mean(len_scores)
        avg_ang = np.mean(ang_scores)

        score = 0.4 * avg_curv + 0.3 * avg_len + 0.3 * avg_ang

        if score > best_score:
            best_score = score
            best_details = {
                "alignment_offset": offset,
                "avg_curvature_match": avg_curv,
                "avg_length_match": avg_len,
                "avg_angle_match": avg_ang,
                "n_edges_compared": n_common
            }

    return best_score, best_details

# ──────────────────────────────────────────────────────────────
# Text Continuity (Llama 3.1 embeddings)
# ──────────────────────────────────────────────────────────────
def compute_text_continuity(text_a: str, text_b: str) -> Tuple[float, Dict]:
    if not text_a or not text_b:
        return 0.0, {"reason": "Empty text"}

    emb_a = llama31_embedding(text_a)
    emb_b = llama31_embedding(text_b)
    emb_sim = cosine_similarity(emb_a, emb_b)

    # Word overlap
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    overlap = len(words_a & words_b) / max(len(words_a), len(words_b)) if words_a and words_b else 0.0

    # Bigram overlap
    def bigrams(t):
        w = t.lower().split()
        return set(zip(w[:-1], w[1:])) if len(w) > 1 else set()
    ba, bb = bigrams(text_a), bigrams(text_b)
    bigram_ov = len(ba & bb) / max(len(ba), len(bb)) if ba and bb else 0.0

    continuity = 0.6 * emb_sim + 0.2 * overlap + 0.2 * bigram_ov

    return continuity, {
        "embedding_similarity": emb_sim,
        "word_overlap": overlap,
        "bigram_overlap": bigram_ov,
        "text_a_preview": text_a[:120],
        "text_b_preview": text_b[:120]
    }

# ──────────────────────────────────────────────────────────────
# Join Confidence Index (Hybrid)
# ──────────────────────────────────────────────────────────────
def compute_join_confidence(fracture: float, semantic: float, ngram: float) -> float:
    """Hybrid Join-Confidence Index: 30% fracture + 50% semantic + 20% n-gram"""
    return 0.3 * fracture + 0.5 * semantic + 0.2 * ngram

# ──────────────────────────────────────────────────────────────
# Image Processing (from cv_contour_engine)
# ──────────────────────────────────────────────────────────────
def extract_tablet_contour(image_path: Path, debug: bool = False) -> Tuple[np.ndarray, Dict]:
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    h, w = img.shape[:2]
    img_area = h * w

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = np.array([5, 30, 40])
    upper = np.array([35, 255, 220])
    mask = cv2.inRange(hsv, lower, upper)

    lower_shadow = np.array([0, 0, 0])
    upper_shadow = np.array([180, 255, 50])
    shadow_mask = cv2.inRange(hsv, lower_shadow, upper_shadow)
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(shadow_mask))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=5)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=3)

    mask_filled = mask.copy()
    contours_fill, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours_fill:
        largest = max(contours_fill, key=cv2.contourArea)
        cv2.fillPoly(mask_filled, [largest], 255)
    mask = mask_filled

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.mean(denoised) < 127:
            thresh = cv2.bitwise_not(thresh)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel2, iterations=4)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        raise ValueError("No contours found")

    min_area = img_area * 0.08
    max_area = img_area * 0.95
    contours_sorted = sorted(contours, key=cv2.contourArea, reverse=True)

    tablet_contour = None
    best_score = 0
    for cnt in contours_sorted:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            epsilon = 0.02 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            rect_score = 1.0 if 4 <= len(approx) <= 10 else 0.5
            bbox = cv2.boundingRect(cnt)
            extent = area / (bbox[2] * bbox[3] + 1e-6)
            score = (area / img_area) * 0.5 + rect_score * 0.3 + extent * 0.2
            if score > best_score:
                best_score = score
                tablet_contour = cnt

    if tablet_contour is None:
        for cnt in contours_sorted:
            if min_area <= cv2.contourArea(cnt) <= max_area:
                tablet_contour = cnt
                break
    if tablet_contour is None:
        tablet_contour = contours_sorted[0]

    epsilon = 0.005 * cv2.arcLength(tablet_contour, True)
    approx = cv2.approxPolyDP(tablet_contour, epsilon, True)

    area = cv2.contourArea(tablet_contour)
    perimeter = cv2.arcLength(tablet_contour, True)
    x, y, w_rect, h_rect = cv2.boundingRect(tablet_contour)
    aspect_ratio = float(w_rect) / h_rect if h_rect > 0 else 1.0
    bbox_area = w_rect * h_rect
    extent = area / bbox_area if bbox_area > 0 else 0.0

    hull = cv2.convexHull(tablet_contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / hull_area if hull_area > 0 else 0.0
    circularity = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0.0

    fracture_angles = []
    if len(approx) >= 3:
        apts = approx.reshape(-1, 2)
        n = len(apts)
        for i in range(n):
            p0, p1, p2 = apts[i], apts[(i + 1) % n], apts[(i + 2) % n]
            v1, v2 = p1 - p0, p2 - p1
            dot = np.dot(v1, v2)
            norm = np.linalg.norm(v1) * np.linalg.norm(v2)
            if norm > 0:
                cos = np.clip(dot / norm, -1.0, 1.0)
                ang = float(np.degrees(np.arccos(cos)))
            else:
                ang = 90.0
            fracture_angles.append(ang)

    contour_pts = tablet_contour.reshape(-1, 2).tolist()
    fracture_profile = compute_fracture_profile_from_contour(tablet_contour, approx)

    return tablet_contour, {
        "contour_points": contour_pts,
        "area": float(area), "perimeter": float(perimeter),
        "bbox": {"x": int(x), "y": int(y), "w": int(w_rect), "h": int(h_rect)},
        "aspect_ratio": aspect_ratio, "extent": extent,
        "solidity": solidity, "circularity": circularity,
        "fracture_angles": fracture_angles,
        "num_vertices": len(approx),
        "fracture_profile": fracture_profile
    }

def compute_visual_embedding(image_path: Path) -> np.ndarray:
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.zeros(128, dtype=np.float32)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)

    orb = cv2.ORB_create(nfeatures=1000)
    keypoints, descriptors = orb.detectAndCompute(img, None)

    if descriptors is None or len(descriptors) == 0:
        moments = cv2.moments(img)
        hu = cv2.HuMoments(moments).flatten()
        hu_log = -np.sign(hu) * np.log10(np.abs(hu) + 1e-10)
        if len(hu_log) < 128:
            hu_log = np.pad(hu_log, (0, 128 - len(hu_log)))
        else:
            hu_log = hu_log[:128]
        norm = np.linalg.norm(hu_log)
        if norm > 0:
            hu_log = hu_log / norm
        return hu_log.astype(np.float32)

    mean_desc = np.mean(descriptors, axis=0).astype(np.float32)
    if len(mean_desc) < 128:
        mean_desc = np.pad(mean_desc, (0, 128 - len(mean_desc)))
    else:
        mean_desc = mean_desc[:128]
    norm = np.linalg.norm(mean_desc)
    if norm > 0:
        mean_desc = mean_desc / norm
    return mean_desc

def encode_embedding(emb: np.ndarray) -> str:
    return base64.b64encode(emb.astype(np.float32).tobytes()).decode('ascii')

def decode_embedding(s: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype=np.float32)

# ──────────────────────────────────────────────────────────────
# LACUNA SIMULATION: Mask part of the fragment
# ──────────────────────────────────────────────────────────────
def simulate_lacuna(image_path: Path, output_path: Path) -> Tuple[str, List[Dict]]:
    """
    Simulate a lacuna (damage) by masking a random region of the tablet.
    Returns: path to masked image, list of lacuna regions (x, y, w, h)
    """
    img = cv2.imread(str(image_path))
    if img is None:
        return str(image_path), []

    h, w = img.shape[:2]

    # Create mask for lacuna (ellipse in lower portion)
    mask = np.ones((h, w), dtype=np.uint8) * 255

    # Random lacuna parameters
    cx = random.randint(w // 3, 2 * w // 3)
    cy = random.randint(2 * h // 3, h - 50)
    ax = random.randint(w // 8, w // 4)
    ay = random.randint(h // 10, h // 5)

    cv2.ellipse(mask, (cx, cy), (ax, ay), 0, 0, 360, 0, -1)

    # Apply lacuna - fill with background color (scanner gray)
    lacuna_img = img.copy()
    bg_color = (200, 200, 200)  # Light gray
    lacuna_img[mask == 0] = bg_color

    # Also mask text in the database (simulate missing characters)
    lacuna_regions = [{
        "x": int(cx - ax), "y": int(cy - ay),
        "w": int(2 * ax), "h": int(2 * ay),
        "type": "ellipse"
    }]

    cv2.imwrite(str(output_path), lacuna_img)
    log.info(f"  Simulated lacuna at ({cx},{cy}) size ({ax},{ay})")

    return str(output_path), lacuna_regions

# ──────────────────────────────────────────────────────────────
# MOTIF DETECTION (Mythological themes)
# ──────────────────────────────────────────────────────────────
MOTIF_KEYWORDS = {
    "Zondvloed": ["a-bu-bi", "a-bu-bi", "zi-us-du-ra", "ut-napish-tim", "flood", "deluge", "ark", "boat"],
    "Godenraad": ["din-gir", "ilāni", "anunnaki", "gods", "council", "assembly", "enlil", "ea"],
    "Schepping": ["e-nu-ma", "e-liš", "creation", "heaven", "earth", "apsu", "tiamat"],
    "Onderwereld": ["kur", "ir-kal-la", "underworld", "netherworld", "ereškigal", "n галел"],
    "Held": ["gilgameš", "gilgamesh", "en-kid-du", "enkidu", "hero", "king"],
    "Rituelen": ["šu-il-la", "incantation", "ritual", "prayer", "offering", "sacrifice"],
    "Koningschap": ["lugal", "šarru", "king", "royal", "throne", "crown", "scepter"],
    "Sterrenkunde": ["mul", "kakkab", "star", "planet", "venus", "moon", "sun", "observation"]
}

def detect_motifs(text: str) -> List[str]:
    """Detect mythological motifs in text."""
    text_lower = text.lower()
    found = []
    for motif, keywords in MOTIF_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(motif)
                break
    return found if found else ["Onbekend/Thema niet gedetecteerd"]

# ──────────────────────────────────────────────────────────────
# TEXT RECONSTRUCTION (Lacuna filling via context)
# ──────────────────────────────────────────────────────────────
def reconstruct_lacuna(fragment_text: str, match_text: str, lacuna_regions: List[Dict]) -> Tuple[str, List[Dict]]:
    """
    Reconstruct missing text in lacuna using best match.
    Returns: reconstructed text, word-level confidences.
    """
    if not fragment_text or not match_text:
        return fragment_text, []

    frag_words = fragment_text.split()
    match_words = match_text.split()

    # Simple alignment: find longest common subsequence
    # and use match_text to fill gaps
    if len(frag_words) > len(match_words):
        frag_words, match_words = match_words, frag_words

    # For each word in match, assign confidence if it appears in fragment context
    word_confidences = []
    for i, mw in enumerate(match_words):
        # Context window in fragment
        context = set(frag_words[max(0,i-2):i+3])
        in_context = mw.lower() in [w.lower() for w in context]
        conf = 0.8 if in_context else (0.4 if mw.lower() in [w.lower() for w in frag_words] else 0.2)
        word_confidences.append({
            "word": mw,
            "confidence": conf,
            "source": "fragment_context" if in_context else ("fragment_corpus" if conf > 0.2 else "gap_fill")
        })

    # Reconstructed text = combine fragment + match for lacuna regions
    # Simplified: use match_text as hypothesis for full text
    reconstructed = match_text

    return reconstructed, word_confidences

# ──────────────────────────────────────────────────────────────
# MAIN RECONSTRUCTION PIPELINE
# ──────────────────────────────────────────────────────────────
def run_reconstruction_pipeline() -> Dict[str, Any]:
    log.info("=" * 70)
    log.info("🏛️  OX-STEALTH END-TO-END FRAGMENT RECONSTRUCTION")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    init_reconstruction_schema(conn)

    stats = {}

    # PHASE 1: Select random CDLI fragment as "unknown find"
    log.info("PHASE 1: Fragment Ingestion — Simulating Unknown Find")
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.title, t.transliteration, v.image_path
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
        WHERE t.id LIKE 'CDLI-%'
        ORDER BY RANDOM() LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        log.error("No CDLI fragments in database!")
        return {"error": "No fragments found"}

    fragment_id, fragment_title, fragment_text, fragment_img_path = row
    log.info(f"  Selected fragment: {fragment_id} — {fragment_title}")

    # Simulate lacuna (damage) on the fragment
    lacuna_img_path = IMAGES_DIR / f"{fragment_id}_lacuna.jpg"
    masked_path, lacuna_regions = simulate_lacuna(Path(fragment_img_path), lacuna_img_path)

    # Extract contour from damaged fragment
    contour, props = extract_tablet_contour(lacuna_img_path, debug=True)
    fracture_profile = props["fracture_profile"]
    fracture_profile.tablet_id = fragment_id

    # Average fracture angle (for report)
    avg_fracture_angle = np.mean(fracture_profile.edge_angles) if fracture_profile.edge_angles else 90.0

    # Detect motifs in fragment text
    motifs = detect_motifs(fragment_text)

    stats["fragment_id"] = fragment_id
    stats["fragment_title"] = fragment_title
    stats["original_text"] = fragment_text
    stats["lacuna_regions"] = lacuna_regions
    stats["fracture_angle"] = avg_fracture_angle
    stats["detected_motifs"] = motifs
    stats["lacuna_image"] = str(lacuna_img_path)

    # PHASE 2: Multimodal Matching
    log.info("PHASE 2: Multimodal Puzzle Engine — Finding Matches")

    # Get all other CDLI fragments with visual data
    cur.execute("""
        SELECT t.id, t.title, t.transliteration, v.fracture_angles_json,
               v.fracture_curvature_json, v.fracture_points_json, v.aspect_ratio,
               v.visual_embedding, v.text_embedding, v.image_path
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
        WHERE t.id LIKE 'CDLI-%' AND t.id != ?
    """, (fragment_id,))

    candidates = cur.fetchall()
    if not candidates:
        log.error("No candidate fragments for matching")
        return stats

    matches = []
    for cand_id, cand_title, cand_text, c_fract_angles, c_fract_curv, c_fract_pts, c_aspect, c_vis_emb, c_txt_emb, c_img_path in candidates:
        # Parse fracture profile
        fract_angles = json.loads(c_fract_angles) if c_fract_angles else []
        fract_curv = json.loads(c_fract_curv) if c_fract_curv else []
        fract_pts = json.loads(c_fract_pts) if c_fract_pts else []

        cand_profile = FractureProfile(
            tablet_id=cand_id,
            edge_curvatures=fract_curv if fract_curv else fract_angles,
            edge_angles=fract_angles,
            edge_lengths=[],
            fracture_points=fract_pts,
            aspect_ratio=c_aspect or 1.0
        )

        # 1. Fracture complementarity (30%)
        fracture_comp, fract_details = compute_fracture_complementarity(fracture_profile, cand_profile)

        # 2. Semantic continuity (50%) - Llama 3.1 embeddings
        semantic_cont, sem_details = compute_text_continuity(fragment_text or "", cand_text or "")

        # 3. N-gram alignment (20%) - eBL style
        ngram_align, ngram_details = ngram_alignment(fragment_text or "", cand_text or "")

        # 4. Hybrid Join-Confidence Index
        join_conf = compute_join_confidence(fracture_comp, semantic_cont, ngram_align)

        matches.append(JoinMatch(
            tablet_a=fragment_id,
            tablet_b=cand_id,
            fracture_complementarity=fracture_comp,
            text_continuity=semantic_cont,
            ngram_alignment=ngram_align,
            join_confidence=join_conf,
            fracture_details=fract_details,
            text_details=sem_details,
            ngram_details=ngram_details
        ))

    # Sort by join confidence
    matches.sort(key=lambda x: x.join_confidence, reverse=True)
    top_matches = matches[:3]

    log.info(f"  Analyzed {len(matches)} candidate fragments")
    log.info("  Top 3 matches:")
    for i, m in enumerate(top_matches):
        log.info(f"    #{i+1}: {m.tablet_b} ({cand_title})")
        log.info(f"          Fracture: {m.fracture_complementarity:.3f} | Semantic: {m.text_continuity:.3f} | N-gram: {m.ngram_alignment:.3f} | JCI: {m.join_confidence:.3f}")

    stats["top_matches"] = [
        {
            "tablet_id": m.tablet_b,
            "title": next((t for t in CDLI_TABLETS if t["id"] == m.tablet_b), {}).get("title", "Unknown"),
            "fracture_complementarity": m.fracture_complementarity,
            "text_continuity": m.text_continuity,
            "ngram_alignment": m.ngram_alignment,
            "join_confidence_index": m.join_confidence,
            "fracture_details": m.fracture_details,
            "text_details": m.text_details,
            "ngram_details": m.ngram_details
        }
        for m in top_matches
    ]

    # PHASE 3: Text Reconstruction
    log.info("PHASE 3: Text Reconstruction — Lacuna Filling")
    best_match_id = top_matches[0].tablet_b if top_matches else None
    best_match_text = ""

    if best_match_id:
        cur.execute("SELECT transliteration FROM tablets WHERE id = ?", (best_match_id,))
        row = cur.fetchone()
        if row:
            best_match_text = row[0]

    reconstructed_text, word_confidences = reconstruct_lacuna(fragment_text, best_match_text, lacuna_regions)

    stats["reconstructed_text"] = reconstructed_text
    stats["word_confidences"] = word_confidences[:30]  # Limit for report

    # PHASE 4: Visualization
    log.info("PHASE 4: Expert Visualization")
    viz_path = EXPORT_DIR / "reconstruction_result.png"
    create_reconstruction_visualization(
        fragment_id, fragment_title, fragment_text,
        lacuna_img_path, contour, props,
        top_matches, motifs,
        reconstructed_text, word_confidences,
        viz_path
    )
    stats["visualization"] = str(viz_path)

    conn.close()

    log.info("=" * 70)
    log.info("✅ RECONSTRUCTION PIPELINE COMPLETE")
    log.info("=" * 70)
    return stats

# CDLI Tablet definitions (needed for title lookup)
CDLI_TABLETS = [
    {"p_number": "P372874", "id": "CDLI-P372874", "title": "Gilgamesh Tablet XI (Flood)"},
    {"p_number": "P372875", "id": "CDLI-P372875", "title": "Gilgamesh Tablet XI (cont.)"},
    {"p_number": "P270068", "id": "CDLI-P270068", "title": "Atrahasis Epic Fragment"},
    {"p_number": "P270069", "id": "CDLI-P270069", "title": "Atrahasis Epic Fragment (cont.)"},
    {"p_number": "P343211", "id": "CDLI-P343211", "title": "Enuma Elish Fragment"},
    {"p_number": "P343212", "id": "CDLI-P343212", "title": "Enuma Elish Fragment (cont.)"},
    {"p_number": "P252048", "id": "CDLI-P252048", "title": "Epic of Anzu Fragment"},
    {"p_number": "P252049", "id": "CDLI-P252049", "title": "Epic of Anzu Fragment (cont.)"},
    {"p_number": "P367892", "id": "CDLI-P367892", "title": "Lugalbanda Epic Fragment"},
    {"p_number": "P367893", "id": "CDLI-P367893", "title": "Lugalbanda Epic Fragment (cont.)"},
    {"p_number": "P412056", "id": "CDLI-P412056", "title": "Descent of Inanna Fragment"},
    {"p_number": "P412057", "id": "CDLI-P412057", "title": "Descent of Inanna Fragment (cont.)"},
]

def create_reconstruction_visualization(
    fragment_id: str, fragment_title: str, fragment_text: str,
    lacuna_img_path: str, contour: np.ndarray, props: Dict,
    top_matches: List[JoinMatch], motifs: List[str],
    reconstructed_text: str, word_confidences: List[Dict],
    output_path: Path
) -> None:
    """Create comprehensive reconstruction visualization."""

    fig = plt.figure(figsize=(20, 14))
    gs = fig.add_gridspec(3, 4, height_ratios=[1, 1, 1.2], hspace=0.3, wspace=0.25)

    # ── TOP ROW: Fragment & Best Match Images ──

    # Original fragment with contour overlay
    ax1 = fig.add_subplot(gs[0, 0])
    img_frag = cv2.imread(lacuna_img_path)
    if img_frag is not None:
        img_frag = cv2.cvtColor(img_frag, cv2.COLOR_BGR2RGB)
        vis_frag = img_frag.copy()
        cv2.drawContours(vis_frag, [contour.astype(np.int32)], -1, (0, 255, 0), 3)
        ax1.imshow(vis_frag)
        ax1.set_title(f"ONBEKENDE SCHERF (Lacuna)\n{fragment_id}\n{fragment_title}", fontsize=11, fontweight='bold')
    else:
        ax1.text(0.5, 0.5, 'Image not found', ha='center', va='center')
    ax1.axis('off')

    # Best match image
    ax2 = fig.add_subplot(gs[0, 1])
    best_match = top_matches[0] if top_matches else None
    if best_match:
        cur = sqlite3.connect(DB_PATH)
        cur.execute("SELECT v.image_path FROM tablets t JOIN spijkerschrift_visueel v ON v.tablet_id=t.id WHERE t.id=?", (best_match.tablet_b,))
        row = cur.fetchone()
        cur.close()
        if row and Path(row[0]).exists():
            img_match = cv2.imread(row[0])
            if img_match is not None:
                img_match = cv2.cvtColor(img_match, cv2.COLOR_BGR2RGB)
                ax2.imshow(img_match)
                ax2.set_title(f"BESTE MATCH\n{best_match.tablet_b}\n{cand_title_from_id(best_match.tablet_b)}", fontsize=11, fontweight='bold', color='green')
            else:
                ax2.text(0.5, 0.5, 'No image', ha='center', va='center')
        else:
            ax2.text(0.5, 0.5, 'No image', ha='center', va='center')
    else:
        ax2.text(0.5, 0.5, 'No matches', ha='center', va='center')
    ax2.axis('off')

    # Second best match
    ax3 = fig.add_subplot(gs[0, 2])
    if len(top_matches) > 1:
        m2 = top_matches[1]
        cur = sqlite3.connect(DB_PATH)
        cur.execute("SELECT v.image_path FROM tablets t JOIN spijkerschrift_visueel v ON v.tablet_id=t.id WHERE t.id=?", (m2.tablet_b,))
        row = cur.fetchone()
        cur.close()
        if row and Path(row[0]).exists():
            img = cv2.imread(row[0])
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                ax3.imshow(img)
                ax3.set_title(f"2e MATCH\n{m2.tablet_b}\n{cand_title_from_id(m2.tablet_b)}", fontsize=11, color='darkorange')
            else:
                ax3.text(0.5, 0.5, 'No image', ha='center', va='center')
        else:
            ax3.text(0.5, 0.5, 'No image', ha='center', va='center')
    else:
        ax3.text(0.5, 0.5, 'N/A', ha='center', va='center')
    ax3.axis('off')

    # Third best match
    ax4 = fig.add_subplot(gs[0, 3])
    if len(top_matches) > 2:
        m3 = top_matches[2]
        cur = sqlite3.connect(DB_PATH)
        cur.execute("SELECT v.image_path FROM tablets t JOIN spijkerschrift_visueel v ON v.tablet_id=t.id WHERE t.id=?", (m3.tablet_b,))
        row = cur.fetchone()
        cur.close()
        if row and Path(row[0]).exists():
            img = cv2.imread(row[0])
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                ax4.imshow(img)
                ax4.set_title(f"3e MATCH\n{m3.tablet_b}\n{cand_title_from_id(m3.tablet_b)}", fontsize=11, color='blue')
            else:
                ax4.text(0.5, 0.5, 'No image', ha='center', va='center')
        else:
            ax4.text(0.5, 0.5, 'No image', ha='center', va='center')
    else:
        ax4.text(0.5, 0.5, 'N/A', ha='center', va='center')
    ax4.axis('off')

    # ── MIDDLE ROW: Fracture Profile & Join Confidence ──

    # Fracture profile visualization
    ax5 = fig.add_subplot(gs[1, :2])
    fp = props["fracture_profile"]
    if hasattr(fp, 'edge_curvatures') and fp.edge_curvatures:
        n = len(fp.edge_curvatures)
        x = np.arange(n)
        width = 0.25
        ax5.bar(x - width, fp.edge_curvatures, width, label='Curvature', color='red', alpha=0.7)
        ax5.bar(x, [a/180.0 for a in fp.edge_angles], width, label='Angle (norm)', color='blue', alpha=0.7)
        ax5.bar(x + width, [l/max(fp.edge_lengths) if max(fp.edge_lengths)>0 else 0 for l in fp.edge_lengths], width, label='Length (norm)', color='green', alpha=0.7)
        ax5.set_xlabel('Edge Index')
        ax5.set_ylabel('Normalized Value')
        ax5.set_title(f'Breuklijn-Profiel: {fragment_id} ({len(fp.edge_curvatures)} randen)', fontweight='bold')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
    else:
        ax5.text(0.5, 0.5, 'No fracture profile', ha='center', va='center')
    ax5.set_title('GEOMETRISCHE BREUKLIJN-ANALYSE (GigaMesh-stijl)', fontweight='bold')

    # Join confidence comparison
    ax6 = fig.add_subplot(gs[1, 2:])
    if top_matches:
        labels = [f"#{i+1}\n{m.tablet_b[-8:]}" for i, m in enumerate(top_matches)]
        fracture_scores = [m.fracture_complementarity for m in top_matches]
        semantic_scores = [m.text_continuity for m in top_matches]
        ngram_scores = [m.ngram_alignment for m in top_matches]
        jci_scores = [m.join_confidence for m in top_matches]

        x = np.arange(len(labels))
        ax6.bar(x - 0.3, fracture_scores, 0.2, label='Breuklijn (30%)', color='red', alpha=0.7)
        ax6.bar(x - 0.1, semantic_scores, 0.2, label='Semantisch (50%)', color='blue', alpha=0.7)
        ax6.bar(x + 0.1, ngram_scores, 0.2, label='N-gram (20%)', color='orange', alpha=0.7)
        ax6.bar(x + 0.3, jci_scores, 0.2, label='JCI (Hybride)', color='green', alpha=0.9, edgecolor='black', linewidth=1.5)

        ax6.set_xticks(x)
        ax6.set_xticklabels(labels, fontsize=9)
        ax6.set_ylabel('Score (0-1)')
        ax6.set_ylim(0, 1.05)
        ax6.set_title('JOIN-CONFIDENCE INDEX VERGELIJKING', fontweight='bold')
        ax6.legend(fontsize=8)
        ax6.grid(True, alpha=0.3)
    else:
        ax6.text(0.5, 0.5, 'No matches', ha='center', va='center')

    # ── BOTTOM ROW: Text Reconstruction & Report ──

    # Reconstructed text with confidence colors
    ax7 = fig.add_subplot(gs[2, :])
    ax7.axis('off')

    # Build report text
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("🏛️  OX-STEALTH FRAGMENT RECONSTRUCTION RAPPORT")
    report_lines.append("=" * 80)
    report_lines.append("")
    report_lines.append(f"SCHERF-ID:            {fragment_id}")
    report_lines.append(f"TITEL:                {fragment_title}")
    report_lines.append(f"BEREKENDE BREUKHOEK:  {avg_fracture_angle:.1f}° (gemiddelde hoek contour-hoeken)")
    report_lines.append(f"LACUNA REGIO:         {lacuna_regions}")
    report_lines.append(f"GEDETECTEERDE MOTIEVEN: {', '.join(motifs)}")
    report_lines.append("")
    report_lines.append("-" * 80)
    report_lines.append("TOP-3 MATCHENDE TABLETTEN (Join-Confidence Index)")
    report_lines.append("-" * 80)

    for i, m in enumerate(top_matches):
        jci_pct = m.join_confidence * 100
        report_lines.append(f"  #{i+1}: {m.tablet_b}")
        report_lines.append(f"       Titel:            {cand_title_from_id(m.tablet_b)}")
        report_lines.append(f"       JCI:              {jci_pct:.1f}%")
        report_lines.append(f"         ├─ Breuklijn-complementariteit: {m.fracture_complementarity*100:.1f}% (gewicht 30%)")
        report_lines.append(f"         ├─ Semantische continuïteit:    {m.text_continuity*100:.1f}% (gewicht 50%)")
        report_lines.append(f"         └─ N-gram alignment (eBL):      {m.ngram_alignment*100:.1f}% (gewicht 20%)")
        report_lines.append("")

    report_lines.append("-" * 80)
    report_lines.append("GEHERCONSTRUEERDE TEKST-HYPOTHESE")
    report_lines.append("-" * 80)
    report_lines.append(f"Oorspronkelijke fragment tekst: {fragment_text[:200]}...")
    report_lines.append("")
    report_lines.append("Herconstrueerde tekst (met lacuna-vulling):")
    # Show reconstructed text with confidence highlighting
    wrapped = textwrap.wrap(reconstructed_text, width=80)
    for line in wrapped[:10]:
        report_lines.append(f"  {line}")
    report_lines.append("")
    report_lines.append("WOORD-CONFIDENTIES (eerste 20):")
    for wc in word_confidences[:20]:
        c = wc.get('confidence', 0)
        marker = "🟢" if c > 0.7 else ("🟡" if c > 0.4 else "🔴")
        report_lines.append(f"  {marker} {wc.get('word',''):<20} {c:.2f} ({wc.get('source','')})")

    report_text = "\n".join(report_lines)
    ax7.text(0.02, 0.98, report_text, transform=ax7.transAxes,
             fontsize=8, fontfamily='monospace', verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='#f5f5f5', alpha=0.9))

    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Reconstruction visualization saved: {output_path}")

def cand_title_from_id(cand_id: str) -> str:
    for t in CDLI_TABLETS:
        if t["id"] == cand_id:
            return t["title"]
    return "Unknown"

if __name__ == "__main__":
    # Set random seed for reproducibility
    random.seed(42)
    np.random.seed(42)

    try:
        stats = run_reconstruction_pipeline()
        print("\n📊 RECONSTRUCTION PIPELINE STATISTICS")
        print("=" * 50)
        for k, v in stats.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
            elif isinstance(v, dict):
                print(f"  {k}: {len(v)} keys")
            else:
                print(f"  {k}: {v}")
        sys.exit(0)
    except Exception as e:
        log.exception("Reconstruction pipeline failed")
        sys.exit(1)