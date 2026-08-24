#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — cv_contour_engine.py
Computer Vision & Contour-Matching Fundament voor spijkerschrift tablets/scherfs.
"""
from __future__ import annotations

import sqlite3
import json
import os
import hashlib
import logging
import sys
import base64
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt

# ──────────────────────────────────────────────────────────────
# Config & Paths
# ──────────────────────────────────────────────────────────────
# Docker mount point is /data, local is ~/Desktop/OxStealthData
DOCKER_DB_PATH = Path("/data/cuneiform_master.db")
LOCAL_DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
DB_PATH = DOCKER_DB_PATH if DOCKER_DB_PATH.exists() else LOCAL_DB_PATH

EXPORT_DIR = Path("/data/export") if Path("/data/export").exists() else (Path.home() / "Desktop" / "OxStealthData" / "export")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ox-stealth-cv")

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class TabletVisual:
    tablet_id: str
    image_path: str
    contour_json: str          # JSON-serialized contour points
    area: float
    perimeter: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    aspect_ratio: float
    extent: float              # area / bbox_area
    solidity: float            # area / hull_area
    circularity: float         # 4*pi*area / perimeter^2
    fracture_angles: str       # JSON list of detected corner angles
    visual_embedding: str      # Base64 encoded feature vector (placeholder)
    created_at: str            # ISO timestamp

@dataclass
class MatchResult:
    tablet_id: str
    visual_similarity: float
    semantic_similarity: float
    combined_score: float
    match_details: Dict

# ──────────────────────────────────────────────────────────────
# Database Schema Extension
# ──────────────────────────────────────────────────────────────
def init_visual_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS spijkerschrift_visueel (
            id TEXT PRIMARY KEY,
            tablet_id TEXT NOT NULL REFERENCES tablets(id),
            image_path TEXT NOT NULL,
            contour_json TEXT NOT NULL,
            area REAL NOT NULL,
            perimeter REAL NOT NULL,
            bbox_x INTEGER NOT NULL,
            bbox_y INTEGER NOT NULL,
            bbox_w INTEGER NOT NULL,
            bbox_h INTEGER NOT NULL,
            aspect_ratio REAL NOT NULL,
            extent REAL NOT NULL,
            solidity REAL NOT NULL,
            circularity REAL NOT NULL,
            fracture_angles_json TEXT NOT NULL,
            visual_embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vis_tablet ON spijkerschrift_visueel(tablet_id);")
    conn.commit()
    log.info("Visual schema initialized")

# ──────────────────────────────────────────────────────────────
# Synthetic Test Image Generator
# ──────────────────────────────────────────────────────────────
def generate_synthetic_tablet(output_path: Path,
                               width: int = 800,
                               height: int = 600,
                               add_cuneiform: bool = True,
                               seed: int = 42,
                               shape_variant: str = "rectangular") -> None:
    """
    Genereer een synthetische kleitablet-afbeelding voor testing.
    Simuleert: zandkleurige achtergrond, ingedrukte tekens, randen, breuklijnen.
    shape_variant: "rectangular", "square", "wide", "tall"
    """
    np.random.seed(seed)

    # 1. Maak een duidelijke achtergrond die VERSCHILT van de tablet
    # Donkerder, neutrale achtergrond (bijv. grijze scanner-bed of zwart)
    bg_color = np.array([30, 30, 30], dtype=np.uint8)  # Zeer donker grijjs - duidelijk contrast
    bg_noise = np.random.normal(0, 8, (height, width, 3)).astype(np.int16)
    img = np.clip(bg_color + bg_noise, 0, 255).astype(np.uint8)

    # 2. Tablet vorm volgens variant
    margin = 80
    if shape_variant == "square":
        # Vierkant: width ~ height
        w = min(width, height) - 2 * margin
        h = w
        offset_x = (width - w) // 2
        offset_y = (height - h) // 2
    elif shape_variant == "wide":
        # Breed: width > height
        w = width - 2 * margin
        h = int(w * 0.6)
        offset_x = margin
        offset_y = (height - h) // 2
    elif shape_variant == "tall":
        # Hoog: height > width
        h = height - 2 * margin
        w = int(h * 0.6)
        offset_x = (width - w) // 2
        offset_y = margin
    else:  # rectangular (default)
        w = width - 2 * margin
        h = height - 2 * margin
        offset_x = margin
        offset_y = margin

    contour_pts = []
    for i, (x, y) in enumerate([
        (offset_x, offset_y),
        (offset_x + w, offset_y),
        (offset_x + w, offset_y + h),
        (offset_x, offset_y + h)
    ]):
        dx = np.random.randint(-5, 6)
        dy = np.random.randint(-5, 6)
        contour_pts.append([x + dx, y + dy])
    contour = np.array(contour_pts, dtype=np.int32).reshape((-1, 1, 2))

    # 3. Tablet kleur: duidelijk onderscheidend van achtergrond (terracotta/bruin)
    # BGR waarde die in HSV valt in H=15-22, S=150-220, V=80-140
    # Terracotta in BGR: ~ [120, 85, 55] -> HSV: H~18, S~180, V~120
    tablet_color = np.array([120, 85, 55], dtype=np.uint8)  # BGR - lichtere terracotta met meer S
    # Minder ruis op de kleur zodat HSV stabiel blijft
    tablet_noise = np.random.normal(0, 10, (height, width, 3)).astype(np.int16)

    # Mask voor tablet gebied
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [contour], 255)

    # Alleen tablet gebied vullen met tablet kleur + tekstuur
    tablet_region = np.clip(tablet_color + tablet_noise, 0, 255).astype(np.uint8)
    img[mask > 0] = tablet_region[mask > 0]

    # 4. Cuneiforme tekens (wedges) simuleren - DONKERDER dan tablet oppervlak (OpenCV only)
    if add_cuneiform:
        n_signs = np.random.randint(15, 30)  # Minder tekens, minder vervuiling HSV
        for _ in range(n_signs):
            cx = np.random.randint(offset_x + 40, offset_x + w - 40)
            cy = np.random.randint(offset_y + 40, offset_y + h - 40)
            sign_type = np.random.choice(['wedge', 'vertical', 'horizontal', 'cross'])
            # Tekens zijn donkerder (ingedrukt in klei) - duidelijk bruin/zwart (BGR)
            color = tuple(np.clip(np.array([40, 30, 20]) + np.random.randint(-10, 10, 3), 10, 80).tolist())
            if sign_type == 'wedge':
                size = np.random.randint(8, 18)
                angle = np.random.uniform(0, 2*np.pi)
                pts = []
                for a in [angle, angle + 2*np.pi/3, angle + 4*np.pi/3]:
                    pts.append([cx + int(size*np.cos(a)), cy + int(size*np.sin(a))])
                cv2.fillPoly(img, [np.array(pts, dtype=np.int32)], color)
            elif sign_type == 'vertical':
                w_sign, h_sign = np.random.randint(4, 8), np.random.randint(18, 35)
                cv2.rectangle(img,
                    (cx - w_sign//2, cy - h_sign//2),
                    (cx + w_sign//2, cy + h_sign//2),
                    color, -1)
            elif sign_type == 'horizontal':
                w_sign, h_sign = np.random.randint(18, 35), np.random.randint(4, 8)
                cv2.rectangle(img,
                    (cx - w_sign//2, cy - h_sign//2),
                    (cx + w_sign//2, cy + h_sign//2),
                    color, -1)
            else:  # cross
                cv2.line(img, (cx-10, cy-10), (cx+10, cy+10), color, 2)
                cv2.line(img, (cx-10, cy+10), (cx+10, cy-10), color, 2)

    # 5. Breuklijnen (random cracks) - subtiel
    for _ in range(np.random.randint(1, 3)):
        pt1 = (np.random.randint(offset_x, offset_x + w), np.random.randint(offset_y, offset_y + h))
        pt2 = (np.random.randint(offset_x, offset_x + w), np.random.randint(offset_y, offset_y + h))
        color = tuple(np.random.randint(60, 120, 3).tolist())
        cv2.line(img, pt1, pt2, color, np.random.randint(1, 2))

    # 6. Schaduw/rand om tablet heen - duidelijk zichtbaar
    cv2.polylines(img, [contour], True, (20, 15, 10), 5)

    cv2.imwrite(str(output_path), img)
    log.info(f"Synthetic tablet generated: {output_path} ({width}x{height}, shape={shape_variant}, tablet_area={w*h})")

# ──────────────────────────────────────────────────────────────
# Contour & Vorm Extractie
# ──────────────────────────────────────────────────────────────
def extract_tablet_contour(image_path: Path, debug: bool = False) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Detecteer contour van tablet in afbeelding.
    Gebruikt kleursegmentatie (HSV) + morfologie om tablet van achtergrond te scheiden.
    Returns: (contour_points Nx2, properties_dict)
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    h, w = img.shape[:2]
    img_area = h * w

    # Converteer naar HSV voor betere kleursegmentatie
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Tablet kleur: specifiek terracotta/bruin bereik
    # Terracotta in HSV: H=10-25, S=80-255, V=50-150
    lower_tablet = np.array([10, 80, 50])
    upper_tablet = np.array([25, 255, 150])
    mask = cv2.inRange(hsv, lower_tablet, upper_tablet)

    # Ook een masque voor de donkere rand/tekens - uitsluiten
    lower_shadow = np.array([0, 0, 0])
    upper_shadow = np.array([180, 255, 60])
    shadow_mask = cv2.inRange(hsv, lower_shadow, upper_shadow)

    # Combineer: tablet gebied ZONDER de donkere rand/tekens
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(shadow_mask))

    # Debug: log HSV statistics
    if debug:
        tablet_pixels = hsv[mask > 0] if np.count_nonzero(mask) > 0 else None
        if tablet_pixels is not None and len(tablet_pixels) > 0:
            log.info(f"  Tablet HSV: H={tablet_pixels[:,0].mean():.0f}±{tablet_pixels[:,0].std():.0f}, "
                     f"S={tablet_pixels[:,1].mean():.0f}±{tablet_pixels[:,1].std():.0f}, "
                     f"V={tablet_pixels[:,2].mean():.0f}±{tablet_pixels[:,2].std():.0f}")
        h_channel = hsv[:,:,0]
        s_channel = hsv[:,:,1]
        v_channel = hsv[:,:,2]
        log.info(f"  Full HSV: H={h_channel.mean():.0f}±{h_channel.std():.0f}, "
                 f"S={s_channel.mean():.0f}±{s_channel.std():.0f}, "
                 f"V={v_channel.mean():.0f}±{v_channel.std():.0f}, "
                 f"mask_pixels={np.count_nonzero(mask)}")

    # Morphological operations om ruis te verwijderen en gaten te dichten
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=4)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)

    # Vul eventuele gaten in de mask
    mask_filled = mask.copy()
    contours_fill, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours_fill:
        largest_fill = max(contours_fill, key=cv2.contourArea)
        cv2.fillPoly(mask_filled, [largest_fill], 255)
    mask = mask_filled

    # Contours vinden in mask
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        # Fallback 1: probeer met bredere HSV range
        lower_tablet2 = np.array([5, 20, 30])
        upper_tablet2 = np.array([35, 255, 220])
        mask2 = cv2.inRange(hsv, lower_tablet2, upper_tablet2)
        mask2 = cv2.morphologyEx(mask2, cv2.MORPH_CLOSE, kernel, iterations=4)
        contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        # Fallback 2: grayscale + Otsu threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Inverteer als Hintergrund donkerder is dan tablet
        if np.mean(denoised) < 127:
            thresh = cv2.bitwise_not(thresh)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel2, iterations=3)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        raise ValueError("No contours found in image")

    # Filter contours: zoek naar de grootste RECHTHOEKIGE contour (tablet vorm)
    min_area = img_area * 0.10  # min 10% van afbeelding
    max_area = img_area * 0.90  # max 90%

    # Sorteer contours op area (grootste eerst)
    contours_sorted = sorted(contours, key=cv2.contourArea, reverse=True)

    tablet_contour = None
    best_score = 0
    for cnt in contours_sorted:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            # Check of het rechthoeckig is
            epsilon = 0.02 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            # Score op basis van: area (groter is beter), rectangulair (4-8 hoeken), extent (dichterbij 1 is beter)
            rect_score = 1.0 if 4 <= len(approx) <= 8 else 0.5
            bbox = cv2.boundingRect(cnt)
            extent = area / (bbox[2] * bbox[3] + 1e-6)
            extent_score = min(extent, 1.0)
            total_score = (area / img_area) * 0.5 + rect_score * 0.3 + extent_score * 0.2
            if total_score > best_score:
                best_score = total_score
                tablet_contour = cnt

    # Fallback: grootste contour in bereik
    if tablet_contour is None:
        for cnt in contours_sorted:
            area = cv2.contourArea(cnt)
            if min_area <= area <= max_area:
                tablet_contour = cnt
                break

    # Fallback: gewoon de grootste
    if tablet_contour is None:
        tablet_contour = contours_sorted[0]

    # Contour vereinfachen (Douglas-Peucker)
    epsilon = 0.005 * cv2.arcLength(tablet_contour, True)
    approx = cv2.approxPolyDP(tablet_contour, epsilon, True)

    # Vorm-eigenschappen berekenen
    area = cv2.contourArea(tablet_contour)
    perimeter = cv2.arcLength(tablet_contour, True)
    x, y, w_rect, h_rect = cv2.boundingRect(tablet_contour)
    aspect_ratio = float(w_rect) / h_rect if h_rect > 0 else 1.0
    bbox_area = w_rect * h_rect
    extent = area / bbox_area if bbox_area > 0 else 0.0

    # Convex hull voor solidity
    hull = cv2.convexHull(tablet_contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / hull_area if hull_area > 0 else 0.0

    # Circularity
    circularity = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0.0

    # Hoeken detecteren (breuklijn-analyse)
    fracture_angles = []
    if len(approx) >= 3:
        pts = approx.reshape(-1, 2)
        n = len(pts)
        for i in range(n):
            p0 = pts[i]
            p1 = pts[(i + 1) % n]
            p2 = pts[(i + 2) % n]
            v1 = p1 - p0
            v2 = p2 - p1
            ang = angle_between(v1, v2)
            fracture_angles.append(float(ang))

    # Contour punten als lijst van [x,y] voor JSON serialisatie
    contour_pts = tablet_contour.reshape(-1, 2).tolist()

    properties = {
        "contour_points": contour_pts,
        "area": float(area),
        "perimeter": float(perimeter),
        "bbox": {"x": int(x), "y": int(y), "w": int(w_rect), "h": int(h_rect)},
        "aspect_ratio": float(aspect_ratio),
        "extent": float(extent),
        "solidity": float(solidity),
        "circularity": float(circularity),
        "fracture_angles": fracture_angles,
        "num_vertices": len(approx)
    }

    if debug:
        log.info(f"  Debug: img_area={img_area}, contour_area={area}, bbox=({w_rect}x{h_rect}), "
                 f"aspect={aspect_ratio:.3f}, extent={extent:.3f}, vertices={len(approx)}, "
                 f"mask_pixels={np.count_nonzero(mask)}, perimeter={perimeter:.0f}")

    return tablet_contour, properties

def angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    """Bereken hoek tussen twee vectoren in graden."""
    dot = np.dot(v1, v2)
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm == 0:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))

# ──────────────────────────────────────────────────────────────
# Visuele Embedding (Placeholder: ORB features + BoVW concept)
# ──────────────────────────────────────────────────────────────
_orb_detector = None

def get_orb_detector():
    global _orb_detector
    if _orb_detector is None:
        _orb_detector = cv2.ORB_create(nfeatures=500)
    return _orb_detector

def compute_visual_embedding(image_path: Path) -> np.ndarray:
    """
    Bereken een visuele feature vector voor de tablet.
    Gebruikt ORB descriptors + Bag-of-Visual-Words (vereenvoudigd: mean pooling).
    Returns: 128-dim float32 vector (genormaliseerd).
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.zeros(128, dtype=np.float32)

    # Contrast enhancement voor betere ORB features
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)

    orb = get_orb_detector()
    keypoints, descriptors = orb.detectAndCompute(img, None)

    if descriptors is None or len(descriptors) == 0:
        # Fallback: gebruik Hu moments als globale vorm descriptor
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

    # Mean pooling van descriptors -> fixed size vector
    mean_desc = np.mean(descriptors, axis=0).astype(np.float32)

    # Pad/truncate naar 128 dims
    if len(mean_desc) < 128:
        mean_desc = np.pad(mean_desc, (0, 128 - len(mean_desc)))
    else:
        mean_desc = mean_desc[:128]

    # L2 normaliseren
    norm = np.linalg.norm(mean_desc)
    if norm > 0:
        mean_desc = mean_desc / norm

    return mean_desc

def encode_embedding(emb: np.ndarray) -> str:
    """Encode numpy array als base64 string voor DB opslag."""
    return base64.b64encode(emb.astype(np.float32).tobytes()).decode('ascii')

def decode_embedding(s: str) -> np.ndarray:
    """Decode base64 string terug naar numpy array."""
    return np.frombuffer(base64.b64decode(s), dtype=np.float32)

# ──────────────────────────────────────────────────────────────
# Multimodale Matching
# ──────────────────────────────────────────────────────────────
def contour_to_vector(contour_pts: List[List[int]], target_len: int = 256) -> np.ndarray:
    """
    Converteer contour punten naar fixed-length vector via resampling.
    Interpoleert contour naar gelijkmatig verdeelde punten.
    """
    if not contour_pts or len(contour_pts) < 3:
        return np.zeros(target_len * 2, dtype=np.float32)

    contour = np.array(contour_pts, dtype=np.float32)

    # Bereken cumulatieve booglengte
    diffs = np.diff(contour, axis=0)
    seg_lens = np.sqrt(np.sum(diffs**2, axis=1))
    cum_len = np.concatenate([[0], np.cumsum(seg_lens)])
    total_len = cum_len[-1]

    if total_len == 0:
        return np.zeros(target_len * 2, dtype=np.float32)

    # Resample naar target_len gelijkmatige punten
    sample_dists = np.linspace(0, total_len, target_len)
    x_interp = np.interp(sample_dists, cum_len, contour[:, 0])
    y_interp = np.interp(sample_dists, cum_len, contour[:, 1])

    # Normaliseer ten opzichte van bounding box
    x_norm = (x_interp - x_interp.min()) / (x_interp.max() - x_interp.min() + 1e-6)
    y_norm = (y_interp - y_interp.min()) / (y_interp.max() - y_interp.min() + 1e-6)

    vector = np.concatenate([x_norm, y_norm]).astype(np.float32)
    return vector

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity tussen twee vectoren."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

def compute_visual_similarity(contour_a: List[List[int]], contour_b: List[List[int]]) -> float:
    """Vorm-gelijkenis tussen twee contouren."""
    vec_a = contour_to_vector(contour_a)
    vec_b = contour_to_vector(contour_b)
    return cosine_similarity(vec_a, vec_b)

def match_fragment_multimodal(conn: sqlite3.Connection,
                              sample_image_path: Path,
                              sample_text: str = "",
                              top_k: int = 5) -> List[MatchResult]:
    """
    Multimodale matching: vorm (contour) + semantiek (tekst embeddings).
    """
    # 1. Extract contour van sample
    _, sample_props = extract_tablet_contour(sample_image_path)
    sample_contour = sample_props["contour_points"]

    # 2. Haal alle bekende tabletten met visuele data op
    cur = conn.cursor()
    cur.execute("""
        SELECT v.tablet_id, v.contour_json, v.visual_embedding,
               t.title, t.language, t.genre
        FROM spijkerschrift_visueel v
        JOIN tablets t ON t.id = v.tablet_id
    """)
    rows = cur.fetchall()

    if not rows:
        log.warning("No visual records in database for matching")
        return []

    results = []
    for tablet_id, contour_json, visual_emb_b64, title, lang, genre in rows:
        ref_contour = json.loads(contour_json)

        # Vorm-similariteit
        visual_sim = compute_visual_similarity(sample_contour, ref_contour)

        # Semantische similariteit (placeholder: 0 als geen tekst/embedding)
        semantic_sim = 0.0
        if sample_text and visual_emb_b64:
            # In productie: vergelijk sample_text embedding met stored embedding
            pass

        # Gecombineerde score (gewogen: 60% vorm, 40% semantiek)
        combined = 0.6 * visual_sim + 0.4 * semantic_sim

        results.append(MatchResult(
            tablet_id=tablet_id,
            visual_similarity=visual_sim,
            semantic_similarity=semantic_sim,
            combined_score=combined,
            match_details={
                "title": title,
                "language": lang,
                "genre": genre,
                "visual_sim": visual_sim,
                "semantic_sim": semantic_sim
            }
        ))

    # Sorteer op combined score
    results.sort(key=lambda x: x.combined_score, reverse=True)
    return results[:top_k]

# ──────────────────────────────────────────────────────────────
# Database Operations
# ──────────────────────────────────────────────────────────────
def store_visual_record(conn: sqlite3.Connection, visual: TabletVisual) -> None:
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO spijkerschrift_visueel
        (id, tablet_id, image_path, contour_json, area, perimeter,
         bbox_x, bbox_y, bbox_w, bbox_h, aspect_ratio, extent,
         solidity, circularity, fracture_angles_json, visual_embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"VIS-{visual.tablet_id}",
        visual.tablet_id,
        visual.image_path,
        visual.contour_json,
        visual.area,
        visual.perimeter,
        visual.bbox_x,
        visual.bbox_y,
        visual.bbox_w,
        visual.bbox_h,
        visual.aspect_ratio,
        visual.extent,
        visual.solidity,
        visual.circularity,
        visual.fracture_angles,
        visual.visual_embedding
    ))
    conn.commit()

def load_all_visual_records(conn: sqlite3.Connection) -> List[Dict]:
    cur = conn.cursor()
    cur.execute("SELECT tablet_id, contour_json, visual_embedding FROM spijkerschrift_visueel")
    return [{"tablet_id": r[0], "contour": json.loads(r[1]), "embedding": r[2]} for r in cur.fetchall()]

# ──────────────────────────────────────────────────────────────
# Visualization Helper
# ──────────────────────────────────────────────────────────────
def visualize_contour(image_path: Path, contour_pts: List[List[int]],
                       properties: Dict, output_path: Path) -> None:
    """Teken contour overlay op originele afbeelding voor debugging."""
    img = cv2.imread(str(image_path))
    contour = np.array(contour_pts, dtype=np.int32).reshape((-1, 1, 2))
    vis = img.copy()
    cv2.drawContours(vis, [contour], -1, (0, 255, 0), 2)

    # Bounding box
    bbox = properties["bbox"]
    cv2.rectangle(vis, (bbox["x"], bbox["y"]),
                  (bbox["x"] + bbox["w"], bbox["y"] + bbox["h"]),
                  (255, 0, 0), 2)

    # Info text
    info_lines = [
        f"Area: {properties['area']:.0f}",
        f"Perimeter: {properties['perimeter']:.0f}",
        f"Aspect: {properties['aspect_ratio']:.2f}",
        f"Extent: {properties['extent']:.2f}",
        f"Solidity: {properties['solidity']:.2f}",
        f"Circularity: {properties['circularity']:.2f}",
        f"Vertices: {properties['num_vertices']}"
    ]
    for i, line in enumerate(info_lines):
        cv2.putText(vis, line, (10, 30 + i*25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.imwrite(str(output_path), vis)
    log.info(f"Contour visualization saved: {output_path}")

# ──────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────
def run_cv_pipeline() -> Dict[str, Any]:
    log.info("=" * 60)
    log.info("🏛️  OX-STEALTH CV CONTOUR ENGINE — Pipeline")
    log.info("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    init_visual_schema(conn)

    stats = {}

    # 1. Genereer 3 DISTINCT synthetische tablets met verschillende vormen
    log.info("PHASE 1: Generate Distinct Synthetic Tablets")
    tablet_configs = [
        {"seed": 42, "width": 800, "height": 600, "name": "tablet_A_rectangular", "shape": "rectangular"},
        {"seed": 123, "width": 700, "height": 700, "name": "tablet_B_square", "shape": "square"},
        {"seed": 456, "width": 900, "height": 500, "name": "tablet_C_wide", "shape": "wide"},
    ]
    tablet_images = []
    for i, cfg in enumerate(tablet_configs):
        img_path = EXPORT_DIR / f"test_{cfg['name']}.png"
        generate_synthetic_tablet(img_path, width=cfg["width"], height=cfg["height"],
                                   seed=cfg["seed"], shape_variant=cfg["shape"])
        tablet_images.append((cfg["name"], img_path))
        stats[f"test_image_{i}"] = str(img_path)

    # 2. Extract contours & embeddings voor elke tablet
    log.info("PHASE 2: Contour & Shape Extraction + Embeddings")
    tablet_data = {}
    for name, img_path in tablet_images:
        contour, properties = extract_tablet_contour(img_path, debug=True)
        visual_emb = compute_visual_embedding(img_path)
        log.info(f"  {name}: Area={properties['area']:.0f}, BBox={properties['bbox']['w']}x{properties['bbox']['h']}, "
                 f"Aspect={properties['aspect_ratio']:.3f}, Vertices={properties['num_vertices']}, "
                 f"Embedding_norm={np.linalg.norm(visual_emb):.4f}")
        tablet_data[name] = {
            "image_path": img_path,
            "contour": properties["contour_points"],
            "properties": properties,
            "embedding": visual_emb
        }

    # 3. Opslaan in DB (koppel aan bestaande tablet IDs)
    log.info("PHASE 3: Store in Database")
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, title FROM tablets LIMIT 3")
        existing_tablets = [(r[0], r[1] or "Unknown") for r in cur.fetchall()]
    except sqlite3.OperationalError:
        existing_tablets = []

    # Map synthetic tablets to existing tablet IDs (or create new)
    for i, (name, data) in enumerate(tablet_data.items()):
        if i < len(existing_tablets):
            tablet_id, title = existing_tablets[i]
        else:
            tablet_id = f"SYNTH-{name}"
            title = f"Synthetic {name}"

        visual = TabletVisual(
            tablet_id=tablet_id,
            image_path=str(data["image_path"]),
            contour_json=json.dumps(data["contour"]),
            area=data["properties"]["area"],
            perimeter=data["properties"]["perimeter"],
            bbox_x=data["properties"]["bbox"]["x"],
            bbox_y=data["properties"]["bbox"]["y"],
            bbox_w=data["properties"]["bbox"]["w"],
            bbox_h=data["properties"]["bbox"]["h"],
            aspect_ratio=data["properties"]["aspect_ratio"],
            extent=data["properties"]["extent"],
            solidity=data["properties"]["solidity"],
            circularity=data["properties"]["circularity"],
            fracture_angles=json.dumps(data["properties"]["fracture_angles"]),
            visual_embedding=encode_embedding(data["embedding"]),
            created_at=""
        )
        store_visual_record(conn, visual)
    log.info(f"Stored visual records for {len(tablet_data)} tablets")

    # 4. Visualisatie van de eerste tablet
    log.info("PHASE 4: Contour Visualization")
    first_name = tablet_images[0][0]
    vis_output = EXPORT_DIR / "test_contour_visualization.png"
    visualize_contour(tablet_data[first_name]["image_path"],
                      tablet_data[first_name]["contour"],
                      tablet_data[first_name]["properties"],
                      vis_output)
    stats["visualization"] = str(vis_output)

    # 5. Multimodale Matching Test: Test elke tablet tegen de anderen
    log.info("PHASE 5: Multimodal Fragment Matching Test (Cross-matching)")
    stats["matches"] = {}
    for query_name, query_data in tablet_data.items():
        matches = match_fragment_multimodal(conn, query_data["image_path"],
                                            sample_text=f"{query_name} text", top_k=3)
        stats["matches"][query_name] = []
        log.info(f"  Query: {query_name}")
        for i, m in enumerate(matches):
            log.info(f"    Match #{i+1}: {m.tablet_id} | Visual: {m.visual_similarity:.4f} | Combined: {m.combined_score:.4f} | {m.match_details.get('title','')}")
            stats["matches"][query_name].append({
                "tablet_id": m.tablet_id,
                "visual_similarity": m.visual_similarity,
                "semantic_similarity": m.semantic_similarity,
                "combined_score": m.combined_score,
                "details": m.match_details
            })

    # 6. Vorm-similariteitsmatrix tussen alle synthetische tablets
    log.info("PHASE 6: Shape Similarity Matrix")
    stats["shape_matrix"] = {}
    names = list(tablet_data.keys())
    for i, name_a in enumerate(names):
        stats["shape_matrix"][name_a] = {}
        for name_b in names:
            if name_a == name_b:
                sim = 1.0
            else:
                sim = compute_visual_similarity(
                    tablet_data[name_a]["contour"],
                    tablet_data[name_b]["contour"]
                )
            stats["shape_matrix"][name_a][name_b] = sim
            log.info(f"  {name_a} <-> {name_b}: {sim:.4f}")

    conn.close()

    log.info("=" * 60)
    log.info("✅ CV CONTOUR ENGINE PIPELINE COMPLETE")
    log.info("=" * 60)
    return stats

if __name__ == "__main__":
    try:
        stats = run_cv_pipeline()
        print("\n📊 CV PIPELINE STATISTICS")
        print("=" * 50)
        for k, v in stats.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
                for item in v[:3]:
                    print(f"    - {item}")
            else:
                print(f"  {k}: {v}")
        sys.exit(0)
    except Exception as e:
        log.exception("CV Pipeline failed")
        sys.exit(1)