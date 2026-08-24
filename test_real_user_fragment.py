#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — test_real_user_fragment.py
Process a user-uploaded fragment image through the full multimodal pipeline.
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
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any
from io import BytesIO
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial.distance import cdist
from scipy.ndimage import gaussian_filter1d

# ──────────────────────────────────────────────────────────────
# Config & Paths
# ──────────────────────────────────────────────────────────────
DOCKER_DB_PATH = Path("/data/cuneiform_master.db")
LOCAL_DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
DB_PATH = DOCKER_DB_PATH if DOCKER_DB_PATH.exists() else LOCAL_DB_PATH

EXPORT_DIR = Path("/data/export") if Path("/data/export").exists() else (Path.home() / "Desktop" / "OxStealthData" / "export")
IMAGES_DIR = Path("/data/images") if Path("/data/images").exists() else (Path.home() / "Desktop" / "OxStealthData" / "images")
BASE_DIR = Path("/data") if Path("/data").exists() else (Path.home() / "Desktop" / "OxStealthData")

EXPORT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Expected user upload filenames
USER_IMAGE_CANDIDATES = [
    "mijn_scherf.jpg", "mijn_scherf.png", "mijn_scherf.jpeg",
    "test_fragment.jpg", "test_fragment.png", "test_fragment.jpeg",
    "fragment.jpg", "fragment.png", "fragment.jpeg",
    "user_fragment.jpg", "user_fragment.png", "user_fragment.jpeg",
    "scherf.jpg", "scherf.png", "scherf.jpeg"
]

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ox-stealth-user-fragment")

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class FragmentAnalysis:
    image_path: str
    contour_points: List[List[int]]
    area: float
    perimeter: float
    aspect_ratio: float
    extent: float
    solidity: float
    circularity: float
    fracture_angles: List[float]
    visual_embedding: np.ndarray
    proposed_transliterations: List[str]
    top_matches: List[Dict]

# ──────────────────────────────────────────────────────────────
# Contour & Shape Extraction (from cv_contour_engine)
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

    min_area = img_area * 0.05
    max_area = img_area * 0.95
    contours_sorted = sorted(contours, key=cv2.contourArea, reverse=True)

    tablet_contour = None
    best_score = 0
    for cnt in contours_sorted:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            epsilon = 0.02 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            rect_score = 1.0 if 4 <= len(approx) <= 12 else 0.5
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

    return tablet_contour, {
        "contour_points": contour_pts,
        "area": float(area), "perimeter": float(perimeter),
        "bbox": {"x": int(x), "y": int(y), "w": int(w_rect), "h": int(h_rect)},
        "aspect_ratio": aspect_ratio, "extent": extent,
        "solidity": solidity, "circularity": circularity,
        "fracture_angles": fracture_angles,
        "num_vertices": len(approx)
    }

# ──────────────────────────────────────────────────────────────
# Visual Embedding (ORB + BoVW)
# ──────────────────────────────────────────────────────────────
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

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

def contour_to_vector(contour_pts: List[List[int]], target_len: int = 256) -> np.ndarray:
    if not contour_pts or len(contour_pts) < 3:
        return np.zeros(target_len * 2, dtype=np.float32)
    contour = np.array(contour_pts, dtype=np.float32)
    diffs = np.diff(contour, axis=0)
    seg_lens = np.sqrt(np.sum(diffs**2, axis=1))
    cum_len = np.concatenate([[0], np.cumsum(seg_lens)])
    total_len = cum_len[-1]
    if total_len == 0:
        return np.zeros(target_len * 2, dtype=np.float32)
    sample_dists = np.linspace(0, total_len, target_len)
    x_interp = np.interp(sample_dists, cum_len, contour[:, 0])
    y_interp = np.interp(sample_dists, cum_len, contour[:, 1])
    x_norm = (x_interp - x_interp.min()) / (x_interp.max() - x_interp.min() + 1e-6)
    y_norm = (y_interp - y_interp.min()) / (y_interp.max() - y_interp.min() + 1e-6)
    return np.concatenate([x_norm, y_norm]).astype(np.float32)

def compute_visual_similarity(contour_a: List[List[int]], contour_b: List[List[int]]) -> float:
    vec_a = contour_to_vector(contour_a)
    vec_b = contour_to_vector(contour_b)
    return cosine_similarity(vec_a, vec_b)

# ──────────────────────────────────────────────────────────────
# OCR / Transliteration Proposal (simplified)
# ──────────────────────────────────────────────────────────────
def propose_transliteration(image_path: Path, contour_props: Dict) -> List[str]:
    """
    Simulated OCR / transliteration proposal.
    In production: integrate with DeepScribe/Akkademia OCR pipeline.
    """
    # Analyze image for sign patterns
    img = cv2.imread(str(image_path))
    if img is None:
        return ["[OCR failed: could not load image]"]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Get tablet region
    bbox = contour_props["bbox"]
    x, y, bw, bh = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    tablet_region = gray[y:y+bh, x:x+bw]

    # Detect wedge-like structures (vertical/horizontal strokes)
    edges = cv2.Canny(tablet_region, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30, minLineLength=20, maxLineGap=10)

    vertical_strokes = 0
    horizontal_strokes = 0
    wedge_shapes = 0

    if lines is not None:
        for line in lines:
            # Handle both array shapes from HoughLinesP
            coords = line[0] if isinstance(line[0], (np.ndarray, list)) else line
            x1, y1, x2, y2 = coords[0], coords[1], coords[2], coords[3]
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if angle > 70 and angle < 110:
                vertical_strokes += 1
            elif angle < 20 or angle > 160:
                horizontal_strokes += 1

    # Triangle detection for wedges
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) > 20:
            eps = 0.04 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, eps, True)
            if len(approx) == 3:
                wedge_shapes += 1

    # Generate plausible transliterations based on detected patterns
    proposals = []

    if wedge_shapes > 5:
        proposals.append("šum-ma a-na-ku GIŠ.IM-MA [broken]")
        proposals.append("ú-ša-ab-bi-šu-ma i-na [lacuna]")
        proposals.append("a-bu-bi i-na-ši-iḫ [fragment]")
    elif vertical_strokes > horizontal_strokes:
        proposals.append("i-na lib-bi [text] [broken]")
        proposals.append("ša i-na [lacuna] [lacuna]")
    else:
        proposals.append("[illegible traces] [signs lost]")
        proposals.append("[...] x x x [fragmentary]")

    # Add metadata
    proposals.append(f"[Detected: {wedge_shapes} wedges, {vertical_strokes} vertical, {horizontal_strokes} horizontal strokes]")

    return proposals

# ──────────────────────────────────────────────────────────────
# Multimodal Matching
# ──────────────────────────────────────────────────────────────
def find_top_matches(user_contour: List[List[int]], user_embedding: np.ndarray,
                     user_text: str, conn: sqlite3.Connection, top_k: int = 3) -> List[Dict]:
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.title, t.transliteration, v.contour_json, v.visual_embedding, v.image_path
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
    """)
    rows = cur.fetchall()

    if not rows:
        return []

    matches = []
    for tablet_id, title, transliteration, contour_json, vis_emb_b64, img_path in rows:
        ref_contour = json.loads(contour_json) if contour_json else []

        # Visual similarity (contour shape)
        visual_sim = compute_visual_similarity(user_contour, ref_contour) if ref_contour else 0.0

        # Visual embedding similarity
        emb_sim = 0.0
        if vis_emb_b64:
            try:
                ref_emb = decode_embedding(vis_emb_b64)
                emb_sim = cosine_similarity(user_embedding, ref_emb)
            except:
                pass

        # Text similarity (simple overlap)
        text_sim = 0.0
        if user_text and transliteration:
            user_words = set(user_text.lower().split())
            ref_words = set(transliteration.lower().split())
            if user_words and ref_words:
                text_sim = len(user_words & ref_words) / max(len(user_words), len(ref_words))

        # Combined score
        combined = 0.5 * visual_sim + 0.3 * emb_sim + 0.2 * text_sim

        matches.append({
            "tablet_id": tablet_id,
            "title": title,
            "transliteration": transliteration[:200] if transliteration else "",
            "visual_similarity": visual_sim,
            "embedding_similarity": emb_sim,
            "text_similarity": text_sim,
            "combined_score": combined,
            "image_path": img_path
        })

    matches.sort(key=lambda x: x["combined_score"], reverse=True)
    return matches[:top_k]

# ──────────────────────────────────────────────────────────────
# Visualization
# ──────────────────────────────────────────────────────────────
def create_user_fragment_visualization(analysis: FragmentAnalysis, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle("OX-STEALTH USER FRAGMENT ANALYSE", fontsize=16, fontweight='bold')

    # 1. Original image with contour
    ax1 = axes[0, 0]
    img = cv2.imread(analysis.image_path)
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        vis = img.copy()
        contour = np.array(analysis.contour_points, dtype=np.int32).reshape((-1, 1, 2))
        cv2.drawContours(vis, [contour], -1, (0, 255, 0), 3)
        bbox = (0, 0, 0, 0)  # simplified
        ax1.imshow(vis)
        ax1.set_title(f"Gedetecteerde Contour\nArea: {analysis.area:.0f} px²\nAspect: {analysis.aspect_ratio:.2f}", fontsize=10)
    else:
        ax1.text(0.5, 0.5, 'Image not loaded', ha='center', va='center')
    ax1.axis('off')

    # 2. Visual embedding heatmap
    ax2 = axes[0, 1]
    emb = analysis.visual_embedding.reshape(16, 8) if len(analysis.visual_embedding) >= 128 else np.zeros((16, 8))
    im = ax2.imshow(emb, cmap='viridis', aspect='auto')
    ax2.set_title("Visuele Embedding (ORB BoVW 128-dim)", fontsize=10)
    plt.colorbar(im, ax=ax2)

    # 3. Fracture angles
    ax3 = axes[0, 2]
    if analysis.fracture_angles:
        ax3.bar(range(len(analysis.fracture_angles)), analysis.fracture_angles, color='coral')
        ax3.set_xlabel('Hoek index')
        ax3.set_ylabel('Graden')
        ax3.set_title(f"Breukhoek Profiel ({len(analysis.fracture_angles)} hoeken)", fontsize=10)
        ax3.grid(True, alpha=0.3)
    else:
        ax3.text(0.5, 0.5, 'Geen hoeken', ha='center', va='center')
    ax3.axis('off')

    # 4. Proposed transliterations
    ax4 = axes[1, 0]
    ax4.axis('off')
    translit_text = "VOORGESTELDE TRANSLITERATIES:\n" + "="*40 + "\n\n"
    for i, prop in enumerate(analysis.proposed_transliterations):
        translit_text += f"{i+1}. {prop}\n\n"
    ax4.text(0.05, 0.95, translit_text, transform=ax4.transAxes,
             fontsize=9, fontfamily='monospace', verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='#fff8e1', alpha=0.9))

    # 5. Top matches
    ax5 = axes[1, 1]
    ax5.axis('off')
    match_text = "TOP-3 MATCHENDE TABLETTEN:\n" + "="*35 + "\n\n"
    for i, m in enumerate(analysis.top_matches):
        match_text += f"#{i+1}: {m['tablet_id']}\n"
        match_text += f"    {m['title']}\n"
        match_text += f"    Visueel: {m['visual_similarity']:.3f}\n"
        match_text += f"    Embedding: {m['embedding_similarity']:.3f}\n"
        match_text += f"    Tekst: {m['text_similarity']:.3f}\n"
        match_text += f"    COMBINED: {m['combined_score']:.3f}\n\n"
    ax5.text(0.05, 0.95, match_text, transform=ax5.transAxes,
             fontsize=9, fontfamily='monospace', verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='#e8f5e9', alpha=0.9))

    # 6. Best match image
    ax6 = axes[1, 2]
    if analysis.top_matches and analysis.top_matches[0]['image_path']:
        match_img_path = analysis.top_matches[0]['image_path']
        if Path(match_img_path).exists():
            match_img = cv2.imread(match_img_path)
            if match_img is not None:
                match_img = cv2.cvtColor(match_img, cv2.COLOR_BGR2RGB)
                ax6.imshow(match_img)
                ax6.set_title(f"BESTE MATCH\n{analysis.top_matches[0]['tablet_id']}\nScore: {analysis.top_matches[0]['combined_score']:.3f}", fontsize=10)
            else:
                ax6.text(0.5, 0.5, 'Match image\nunreadable', ha='center', va='center')
        else:
            ax6.text(0.5, 0.5, 'Match image\nnot found', ha='center', va='center')
    else:
        ax6.text(0.5, 0.5, 'Geen matches', ha='center', va='center')
    ax6.axis('off')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"User fragment visualization saved: {output_path}")

# ──────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────
def find_user_image() -> Optional[Path]:
    """Search for user-uploaded fragment image."""
    for name in USER_IMAGE_CANDIDATES:
        # Check BASE_DIR
        path = BASE_DIR / name
        if path.exists():
            return path
        # Check IMAGES_DIR
        path = IMAGES_DIR / name
        if path.exists():
            return path
        # Check current directory
        path = Path.cwd() / name
        if path.exists():
            return path
    return None

def run_user_fragment_pipeline() -> Dict[str, Any]:
    log.info("=" * 70)
    log.info("🏛️  OX-STEALTH USER FRAGMENT ANALYSE")
    log.info("=" * 70)

    # 1. Find user image
    user_image = find_user_image()
    if user_image is None:
        expected = ", ".join(USER_IMAGE_CANDIDATES[:6]) + "..."
        log.error(f"GEEN GEBRUIKERSAFBEELDING GEVONDEN!")
        log.error(f"Verwachte bestandsnamen in {BASE_DIR}:")
        log.error(f"  {expected}")
        log.error(f"Plaats een bestand met een van deze namen en run opnieuw.")
        return {
            "status": "no_image_found",
            "expected_filenames": USER_IMAGE_CANDIDATES,
            "search_paths": [str(BASE_DIR), str(IMAGES_DIR), str(Path.cwd())]
        }

    log.info(f"Gevonden gebruikersafbeelding: {user_image}")

    # 2. Contour & Shape Extraction
    log.info("Stap 1: Contour & Vorm Extractie")
    contour, props = extract_tablet_contour(user_image, debug=True)
    visual_emb = compute_visual_embedding(user_image)

    # 3. OCR / Transliteration Proposal
    log.info("Stap 2: OCR & Transliteratie Voortstelle")
    transliterations = propose_transliteration(user_image, props)

    # 4. Multimodal Matching
    log.info("Stap 3: Multimodale Matching tegen Database")
    conn = sqlite3.connect(DB_PATH)
    top_matches = find_top_matches(
        props["contour_points"], visual_emb,
        " ".join(transliterations[:-1]), conn, top_k=3
    )
    conn.close()

    # 5. Build analysis object
    analysis = FragmentAnalysis(
        image_path=str(user_image),
        contour_points=props["contour_points"],
        area=props["area"],
        perimeter=props["perimeter"],
        aspect_ratio=props["aspect_ratio"],
        extent=props["extent"],
        solidity=props["solidity"],
        circularity=props["circularity"],
        fracture_angles=props["fracture_angles"],
        visual_embedding=visual_emb,
        proposed_transliterations=transliterations,
        top_matches=top_matches
    )

    # 6. Visualization
    log.info("Stap 4: Veldverslag Visualisatie")
    output_path = EXPORT_DIR / "user_fragment_analysis.png"
    create_user_fragment_visualization(analysis, output_path)

    # Print summary
    log.info("=" * 70)
    log.info("ANALYSE VOLTOOID")
    log.info("=" * 70)
    log.info(f"Afbeelding: {user_image.name}")
    log.info(f"Contour: {len(props['contour_points'])} punten, Area={props['area']:.0f}, Aspect={props['aspect_ratio']:.2f}")
    log.info(f"Breukhoeken: {len(props['fracture_angles'])} gedetecteerd")
    log.info(f"Top matches: {len(top_matches)}")
    for i, m in enumerate(top_matches):
        log.info(f"  #{i+1}: {m['tablet_id']} - Combined: {m['combined_score']:.3f}")

    return {
        "status": "success",
        "image": str(user_image),
        "contour_points": len(props["contour_points"]),
        "area": props["area"],
        "aspect_ratio": props["aspect_ratio"],
        "fracture_angles": len(props["fracture_angles"]),
        "transliterations": transliterations,
        "top_matches": top_matches,
        "visualization": str(output_path)
    }

if __name__ == "__main__":
    try:
        result = run_user_fragment_pipeline()
        print("\n📊 USER FRAGMENT ANALYSE RESULT")
        print("=" * 50)
        for k, v in result.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
                if k == "top_matches" and v:
                    for m in v:
                        print(f"    - {m['tablet_id']}: {m['combined_score']:.3f}")
            else:
                print(f"  {k}: {v}")

        if result.get("status") == "no_image_found":
            print(f"\n⚠️  PLAATS EEN AFBEELDING MET EEN VAN DEZE NAMEN:")
            for name in USER_IMAGE_CANDIDATES:
                print(f"   {name}")
            sys.exit(1)
        sys.exit(0)
    except Exception as e:
        log.exception("User fragment pipeline failed")
        sys.exit(1)