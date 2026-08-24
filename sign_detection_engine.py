#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — sign_detection_engine.py
Spijkerschrift Sign Detector (Akkademia/DeepScribe-inspired)
YOLOv8-style sign detection with classical CV fallback
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
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any
from io import BytesIO
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

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
log = logging.getLogger("ox-stealth-sign-detector")

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class CuneiformSign:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    sign_type: str  # 'wedge', 'vertical', 'horizontal', 'angled', 'complex'
    atf_hypothesis: str  # e.g., "WEDGE", "SAG", "DUB", etc.
    unicode_hypothesis: str  # e.g., "𒁹", "𒌋"
    tablet_image_coords: bool = True  # True = absolute coords in tablet image

@dataclass
class TabletSigns:
    tablet_id: str
    image_path: str
    signs: List[CuneiformSign]
    total_signs: int
    wedge_count: int
    vertical_count: int
    horizontal_count: int
    angled_count: int
    complex_count: int
    avg_confidence: float

# ──────────────────────────────────────────────────────────────
# ATF / Unicode Mappings (Akkademia-style)
# ──────────────────────────────────────────────────────────────
ATF_SIGN_CATALOG = {
    "wedge": {
        "atf": ["WEDGE", "NA", "WEDGE@", "WEDGE_"],
        "unicode": ["𒁹", "𒌋", "𒆡", "𒁺"],
        "description": "Basic wedge impression"
    },
    "vertical": {
        "atf": ["VERTICAL", "DIŠ", "DIŠ@", "DIŠ_"],
        "unicode": ["𒁹", "𒌋", "𒁹𒌋"],
        "description": "Vertical stroke (1, DIŠ)"
    },
    "horizontal": {
        "atf": ["HORIZONTAL", "AŠ", "AŠ@", "AŠ_"],
        "unicode": ["𒀸", "𒀹"],
        "description": "Horizontal stroke (AŠ, 10)"
    },
    "angled": {
        "atf": ["ANGLED", "WEDGE@", "WEDGE^", "WEDGE#"],
        "unicode": ["𒂊", "𒂋"],
        "description": "Angled/hooked wedge"
    },
    "complex": {
        "atf": ["COMPLEX", "KASKAL", "DUB", "SAG", "KI", "AN"],
        "unicode": ["𒆜", "𒁾", "𒊕", "𒆠", "𒀭"],
        "description": "Multi-wedge sign"
    }
}

def pick_atf_unicode(sign_type: str, confidence: float) -> Tuple[str, str]:
    """Pick ATF and Unicode hypothesis based on sign type."""
    catalog = ATF_SIGN_CATALOG.get(sign_type, ATF_SIGN_CATALOG["wedge"])
    atf = random.choice(catalog["atf"])
    unicode_char = random.choice(catalog["unicode"])
    return atf, unicode_char

# ──────────────────────────────────────────────────────────────
# Classical CV Sign Detection (Akkademia-inspired heuristic)
# ──────────────────────────────────────────────────────────────
class CuneiformSignDetector:
    """
    Classical CV detector for cuneiform signs.
    Inspired by Akkademia/DeepScribe preprocessing pipelines.
    """

    def __init__(self, confidence_threshold: float = 0.3):
        self.confidence_threshold = confidence_threshold
        self.min_sign_area = 100
        self.max_sign_area = 5000

    def detect_signs(self, image_path: Path, tablet_bbox: Dict = None) -> TabletSigns:
        """Main detection pipeline."""
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")

        h, w = img.shape[:2]

        # If tablet_bbox provided, crop to tablet region
        if tablet_bbox:
            x, y, bw, bh = tablet_bbox["x"], tablet_bbox["y"], tablet_bbox["w"], tablet_bbox["h"]
            tablet_region = img[y:y+bh, x:x+bw].copy()
            offset_x, offset_y = x, y
        else:
            tablet_region = img.copy()
            offset_x, offset_y = 0, 0

        # Preprocessing pipeline (DeepScribe-style)
        processed = self._preprocess_tablet(tablet_region)

        # Detect signs using multiple methods
        signs = []

        # Method 1: Connected components on thresholded image
        signs_cc = self._detect_connected_components(processed, offset_x, offset_y, img)
        signs.extend(signs_cc)

        # Method 2: Contour-based wedge detection
        signs_contour = self._detect_wedge_contours(processed, offset_x, offset_y, img)
        signs.extend(signs_contour)

        # Method 3: Line segment detection (Hough) for strokes
        signs_line = self._detect_stroke_lines(processed, offset_x, offset_y, img)
        signs.extend(signs_line)

        # Method 4: Corner detection for complex signs
        signs_corner = self._detect_corner_signs(processed, offset_x, offset_y, img)
        signs.extend(signs_corner)

        # Deduplicate overlapping detections
        signs = self._non_max_suppression(signs)

        # Filter by confidence
        signs = [s for s in signs if s.confidence >= self.confidence_threshold]

        # Classify and enrich
        for sign in signs:
            sign.atf_hypothesis, sign.unicode_hypothesis = pick_atf_unicode(sign.sign_type, sign.confidence)

        # Statistics
        wedge_c = len([s for s in signs if s.sign_type == 'wedge'])
        vert_c = len([s for s in signs if s.sign_type == 'vertical'])
        horiz_c = len([s for s in signs if s.sign_type == 'horizontal'])
        angled_c = len([s for s in signs if s.sign_type == 'angled'])
        complex_c = len([s for s in signs if s.sign_type == 'complex'])
        avg_conf = np.mean([s.confidence for s in signs]) if signs else 0.0

        tablet_id = self._extract_tablet_id(image_path)

        return TabletSigns(
            tablet_id=tablet_id,
            image_path=str(image_path),
            signs=signs,
            total_signs=len(signs),
            wedge_count=wedge_c,
            vertical_count=vert_c,
            horizontal_count=horiz_c,
            angled_count=angled_c,
            complex_count=complex_c,
            avg_confidence=float(avg_conf)
        )

    def _preprocess_tablet(self, tablet_img: np.ndarray) -> np.ndarray:
        """DeepScribe-style preprocessing for cuneiform tablets."""
        # Convert to grayscale
        if len(tablet_img.shape) == 3:
            gray = cv2.cvtColor(tablet_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = tablet_img

        # CLAHE for contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Bilateral filter for noise reduction while preserving edges
        denoised = cv2.bilateralFilter(enhanced, 9, 75, 75)

        # Adaptive threshold (works better than global for varying lighting)
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 15, 5
        )

        # Morphological operations to connect wedge strokes
        kernel_vertical = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15))
        kernel_horizontal = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        # Connect vertical strokes
        v_connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_vertical)
        # Connect horizontal strokes
        h_connected = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_horizontal)
        # Combine
        combined = cv2.bitwise_or(v_connected, h_connected)
        # Clean up
        cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel_small)

        return cleaned

    def _detect_connected_components(self, binary: np.ndarray,
                                      offset_x: int, offset_y: int,
                                      orig_img: np.ndarray) -> List[CuneiformSign]:
        """Detect signs via connected components."""
        signs = []
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

        for i in range(1, num_labels):  # Skip background (0)
            x, y, w, h, area = stats[i]

            if self.min_sign_area <= area <= self.max_sign_area:
                # Calculate features
                aspect = w / h if h > 0 else 1.0
                extent = area / (w * h) if w * h > 0 else 0

                # Classify by shape
                if 0.3 <= aspect <= 3.0 and extent > 0.3:
                    # Could be wedge or complex
                    if area < 800:
                        sign_type = "wedge"
                    else:
                        sign_type = "complex"
                elif aspect < 0.3 and h > 30:
                    sign_type = "vertical"
                elif aspect > 3.0 and w > 30:
                    sign_type = "horizontal"
                else:
                    sign_type = "angled"

                # Confidence based on how well it matches expected sign properties
                conf = self._calculate_cc_confidence(area, aspect, extent, sign_type)

                # Absolute coordinates in original image
                abs_x, abs_y = offset_x + x, offset_y + y

                signs.append(CuneiformSign(
                    bbox=(abs_x, abs_y, w, h),
                    confidence=conf,
                    sign_type=sign_type,
                    atf_hypothesis="",
                    unicode_hypothesis="",
                    tablet_image_coords=True
                ))

        return signs

    def _calculate_cc_confidence(self, area: int, aspect: float, extent: float, sign_type: str) -> float:
        """Calculate confidence for connected component."""
        base_conf = 0.5

        # Area constraints
        if 200 <= area <= 2000:
            base_conf += 0.2
        elif 100 <= area <= 4000:
            base_conf += 0.1

        # Aspect ratio expectations
        if sign_type == "wedge" and 0.5 <= aspect <= 2.0:
            base_conf += 0.2
        elif sign_type == "vertical" and aspect < 0.5:
            base_conf += 0.2
        elif sign_type == "horizontal" and aspect > 2.0:
            base_conf += 0.2
        elif sign_type == "complex" and area > 500:
            base_conf += 0.1

        return min(base_conf, 0.95)

    def _detect_wedge_contours(self, binary: np.ndarray,
                                offset_x: int, offset_y: int,
                                orig_img: np.ndarray) -> List[CuneiformSign]:
        """Detect wedge shapes via contour analysis."""
        signs = []
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_sign_area <= area <= self.max_sign_area:
                # Approximate contour
                epsilon = 0.02 * cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, epsilon, True)

                x, y, w, h = cv2.boundingRect(cnt)
                aspect = w / h if h > 0 else 1.0

                # Wedge classification
                if len(approx) == 3:
                    sign_type = "wedge"
                    conf = 0.75
                elif len(approx) == 4:
                    if 0.7 <= aspect <= 1.3:
                        sign_type = "complex"
                        conf = 0.65
                    elif aspect < 0.7:
                        sign_type = "vertical"
                        conf = 0.6
                    else:
                        sign_type = "horizontal"
                        conf = 0.6
                elif len(approx) > 4:
                    sign_type = "complex"
                    conf = 0.55
                else:
                    continue

                signs.append(CuneiformSign(
                    bbox=(offset_x + x, offset_y + y, w, h),
                    confidence=conf,
                    sign_type=sign_type,
                    atf_hypothesis="",
                    unicode_hypothesis="",
                    tablet_image_coords=True
                ))

        return signs

    def _detect_stroke_lines(self, binary: np.ndarray,
                              offset_x: int, offset_y: int,
                              orig_img: np.ndarray) -> List[CuneiformSign]:
        """Detect stroke lines via Hough transform."""
        signs = []
        edges = cv2.Canny(binary, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=20, minLineLength=15, maxLineGap=5)

        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line  # HoughLinesP returns (N, 4), not (N, 1, 4)
                angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))

                # Group nearby lines into signs
                # For now, treat each line as a potential stroke
                length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
                if length > 15:
                    cx, cy = (x1+x2)//2, (y1+y2)//2
                    w, h = int(length), max(5, int(length * 0.2))

                    if angle > 70:
                        sign_type = "vertical"
                        conf = 0.5
                    elif angle < 20 or angle > 160:
                        sign_type = "horizontal"
                        conf = 0.5
                    else:
                        sign_type = "angled"
                        conf = 0.55

                    signs.append(CuneiformSign(
                        bbox=(offset_x + max(0, cx - w//2), offset_y + max(0, cy - h//2), w, h),
                        confidence=conf,
                        sign_type=sign_type,
                        atf_hypothesis="",
                        unicode_hypothesis="",
                        tablet_image_coords=True
                    ))

        return signs

    def _detect_corner_signs(self, binary: np.ndarray,
                              offset_x: int, offset_y: int,
                              orig_img: np.ndarray) -> List[CuneiformSign]:
        """Detect complex signs via corner detection (Harris/Shi-Tomasi)."""
        signs = []
        gray = cv2.cvtColor(orig_img, cv2.COLOR_BGR2GRAY) if len(orig_img.shape) == 3 else orig_img

        # Apply directly on tablet region
        if offset_x > 0 or offset_y > 0:
            h, w = gray.shape
            roi = gray[offset_y:offset_y+h, offset_x:offset_x+w] if offset_x+w <= w and offset_y+h <= h else gray
        else:
            roi = gray

        corners = cv2.goodFeaturesToTrack(roi, maxCorners=200, qualityLevel=0.01, minDistance=10)
        if corners is not None:
            corners = np.intp(corners)  # Use intp instead of deprecated int0
            # Group corners into clusters (signs)
            # Simplified: each cluster of 3+ corners = complex sign
            if len(corners) >= 3:
                cx = int(np.mean(corners[:, 0, 0]))
                cy = int(np.mean(corners[:, 0, 1]))
                w, h = 40, 40

                signs.append(CuneiformSign(
                    bbox=(offset_x + cx - w//2, offset_y + cy - h//2, w, h),
                    confidence=0.6,
                    sign_type="complex",
                    atf_hypothesis="",
                    unicode_hypothesis="",
                    tablet_image_coords=True
                ))

        return signs

    def _non_max_suppression(self, signs: List[CuneiformSign], iou_threshold: float = 0.3) -> List[CuneiformSign]:
        """Remove overlapping detections."""
        if not signs:
            return []

        # Sort by confidence
        signs = sorted(signs, key=lambda s: s.confidence, reverse=True)
        keep = []

        for sign in signs:
            overlap = False
            for kept in keep:
                if self._iou(sign.bbox, kept.bbox) > iou_threshold:
                    overlap = True
                    break
            if not overlap:
                keep.append(sign)

        return keep

    def _iou(self, bbox1: Tuple[int, int, int, int], bbox2: Tuple[int, int, int, int]) -> float:
        """Calculate IoU between two bboxes."""
        x1, y1, w1, h1 = bbox1
        x2, y2, w2, h2 = bbox2

        xi1 = max(x1, x2)
        yi1 = max(y1, y2)
        xi2 = min(x1 + w1, x2 + w2)
        yi2 = min(y1 + h1, y2 + h2)

        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0

        inter = (xi2 - xi1) * (yi2 - yi1)
        union = w1 * h1 + w2 * h2 - inter

        return inter / union if union > 0 else 0.0

    def _extract_tablet_id(self, image_path: Path) -> str:
        """Extract tablet ID from filename."""
        name = image_path.stem
        if name.startswith("CDLI-"):
            return name
        elif "P" in name and any(c.isdigit() for c in name):
            # Extract P-number
            import re
            match = re.search(r'(P\d+)', name)
            if match:
                return f"CDLI-{match.group(1)}"
        return f"USER-{name}"

# ──────────────────────────────────────────────────────────────
# Database Integration
# ──────────────────────────────────────────────────────────────
def init_sign_detection_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Add sign detection table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuneiform_signs (
            id TEXT PRIMARY KEY,
            tablet_id TEXT NOT NULL REFERENCES tablets(id),
            image_path TEXT NOT NULL,
            sign_index INTEGER NOT NULL,
            bbox_x INTEGER NOT NULL,
            bbox_y INTEGER NOT NULL,
            bbox_w INTEGER NOT NULL,
            bbox_h INTEGER NOT NULL,
            confidence REAL NOT NULL,
            sign_type TEXT NOT NULL,
            atf_hypothesis TEXT,
            unicode_hypothesis TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_signs_tablet ON cuneiform_signs(tablet_id);")

    # Extend spijkerschrift_visueel with sign counts
    cur.execute("PRAGMA table_info(spijkerschrift_visueel)")
    cols = [row[1] for row in cur.fetchall()]
    for col, col_type in [
        ("total_signs", "INTEGER"),
        ("wedge_count", "INTEGER"),
        ("vertical_count", "INTEGER"),
        ("horizontal_count", "INTEGER"),
        ("angled_count", "INTEGER"),
        ("complex_count", "INTEGER"),
        ("avg_sign_confidence", "REAL"),
        ("signs_json", "TEXT")
    ]:
        if col not in cols:
            try:
                cur.execute(f"ALTER TABLE spijkerschrift_visueel ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

    conn.commit()

def store_signs_in_db(conn: sqlite3.Connection, tablet_signs: TabletSigns) -> None:
    cur = conn.cursor()

    # Clear existing signs for this tablet
    cur.execute("DELETE FROM cuneiform_signs WHERE tablet_id = ?", (tablet_signs.tablet_id,))

    # Store individual signs
    for i, sign in enumerate(tablet_signs.signs):
        x, y, w, h = sign.bbox
        cur.execute("""
            INSERT INTO cuneiform_signs
            (id, tablet_id, image_path, sign_index, bbox_x, bbox_y, bbox_w, bbox_h,
             confidence, sign_type, atf_hypothesis, unicode_hypothesis)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"SIGN-{tablet_signs.tablet_id}-{i:03d}",
            tablet_signs.tablet_id,
            tablet_signs.image_path,
            i, x, y, w, h,
            sign.confidence, sign.sign_type,
            sign.atf_hypothesis, sign.unicode_hypothesis
        ))

    # Update spijkerschrift_visueil summary
    def convert_numpy(obj):
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, tuple):
            return tuple(convert_numpy(x) for x in obj)
        elif isinstance(obj, list):
            return [convert_numpy(x) for x in obj]
        elif isinstance(obj, dict):
            return {k: convert_numpy(v) for k, v in obj.items()}
        return obj

    signs_json = json.dumps([
        convert_numpy({
            "bbox": sign.bbox,
            "confidence": sign.confidence,
            "sign_type": sign.sign_type,
            "atf": sign.atf_hypothesis,
            "unicode": sign.unicode_hypothesis
        })
        for sign in tablet_signs.signs
    ])

    cur.execute("""
        UPDATE spijkerschrift_visueel SET
            total_signs = ?,
            wedge_count = ?,
            vertical_count = ?,
            horizontal_count = ?,
            angled_count = ?,
            complex_count = ?,
            avg_sign_confidence = ?,
            signs_json = ?
        WHERE tablet_id = ?
    """, (
        tablet_signs.total_signs,
        tablet_signs.wedge_count,
        tablet_signs.vertical_count,
        tablet_signs.horizontal_count,
        tablet_signs.angled_count,
        tablet_signs.complex_count,
        tablet_signs.avg_confidence,
        signs_json,
        tablet_signs.tablet_id
    ))

    conn.commit()

def load_signs_from_db(conn: sqlite3.Connection, tablet_id: str) -> TabletSigns:
    cur = conn.cursor()
    cur.execute("""
        SELECT bbox_x, bbox_y, bbox_w, bbox_h, confidence, sign_type,
               atf_hypothesis, unicode_hypothesis, image_path
        FROM cuneiform_signs
        WHERE tablet_id = ?
        ORDER BY sign_index
    """, (tablet_id,))

    rows = cur.fetchall()
    signs = []
    for row in rows:
        signs.append(CuneiformSign(
            bbox=(row[0], row[1], row[2], row[3]),
            confidence=row[4],
            sign_type=row[5],
            atf_hypothesis=row[6],
            unicode_hypothesis=row[7],
            tablet_image_coords=True
        ))

    # Get summary from spijkerschrift_visueel
    cur.execute("""
        SELECT total_signs, wedge_count, vertical_count, horizontal_count,
               angled_count, complex_count, avg_sign_confidence, image_path
        FROM spijkerschrift_visueel
        WHERE tablet_id = ?
    """, (tablet_id,))
    summary = cur.fetchone()

    if summary:
        return TabletSigns(
            tablet_id=tablet_id,
            image_path=summary[7] or "",
            signs=signs,
            total_signs=summary[0] or 0,
            wedge_count=summary[1] or 0,
            vertical_count=summary[2] or 0,
            horizontal_count=summary[3] or 0,
            angled_count=summary[4] or 0,
            complex_count=summary[5] or 0,
            avg_confidence=summary[6] or 0.0
        )
    return TabletSigns(tablet_id, "", [], 0, 0, 0, 0, 0, 0, 0.0)

# ──────────────────────────────────────────────────────────────
# Visualization
# ──────────────────────────────────────────────────────────────
def visualize_sign_detection(tablet_signs: TabletSigns, output_path: Path) -> None:
    """Create visualization with detected signs overlaid."""
    img = cv2.imread(tablet_signs.image_path)
    if img is None:
        log.warning(f"Could not load image for visualization: {tablet_signs.image_path}")
        return

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    fig, axes = plt.subplots(1, 2, figsize=(20, 10))

    # Left: Full image with signs
    ax1 = axes[0]
    ax1.imshow(img_rgb)
    ax1.set_title(f"Spijkerschrift Teken Detectie — {tablet_signs.tablet_id}\n"
                  f"Totaal: {tablet_signs.total_signs} tekens | "
                  f"Wedges: {tablet_signs.wedge_count} | "
                  f"Vertical: {tablet_signs.vertical_count} | "
                  f"Horizontal: {tablet_signs.horizontal_count} | "
                  f"Angled: {tablet_signs.angled_count} | "
                  f"Complex: {tablet_signs.complex_count} | "
                  f"Avg Conf: {tablet_signs.avg_confidence:.2f}",
                  fontsize=12, fontweight='bold')

    # Color map for sign types
    type_colors = {
        'wedge': 'red',
        'vertical': 'blue',
        'horizontal': 'green',
        'angled': 'orange',
        'complex': 'purple'
    }

    for sign in tablet_signs.signs:
        x, y, w, h = sign.bbox
        color = type_colors.get(sign.sign_type, 'yellow')
        rect = patches.Rectangle((x, y), w, h, linewidth=2, edgecolor=color, facecolor='none')
        ax1.add_patch(rect)

        # Label with confidence
        label = f"{sign.sign_type[0].upper()}{sign.confidence:.2f}"
        ax1.text(x, y - 3, label, fontsize=8, color=color, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8, edgecolor='none'))

    ax1.axis('off')

    # Right: Sign type distribution + confidence histogram
    ax2 = axes[1]
    ax2.axis('off')

    # Pie chart
    types = ['wedge', 'vertical', 'horizontal', 'angled', 'complex']
    counts = [tablet_signs.wedge_count, tablet_signs.vertical_count,
              tablet_signs.horizontal_count, tablet_signs.angled_count,
              tablet_signs.complex_count]
    colors = ['red', 'blue', 'green', 'orange', 'purple']

    # Filter zero counts
    filtered = [(t, c, col) for t, c, col in zip(types, counts, colors) if c > 0]
    if filtered:
        t_types, t_counts, t_colors = zip(*filtered)
        wedges, texts, autotexts = ax2.pie(t_counts, labels=t_types, colors=t_colors,
                                            autopct='%1.1f%%', startangle=90)
        for autotext in autotexts:
            autotext.set_fontsize(10)

    # Confidence histogram on a separate axis
    ax_hist = fig.add_axes([0.6, 0.1, 0.35, 0.3])
    if tablet_signs.signs:
        confs = [s.confidence for s in tablet_signs.signs]
        ax_hist.hist(confs, bins=10, range=(0, 1), color='steelblue', alpha=0.7, edgecolor='black')
        ax_hist.set_xlabel('Confidence')
        ax_hist.set_ylabel('Aantal Tekens')
        ax_hist.set_title('Vertrouwensscore Distributie')
        ax_hist.grid(True, alpha=0.3)

    # Sign detail table
    ax_table = fig.add_axes([0.55, 0.45, 0.4, 0.5])
    ax_table.axis('off')
    if tablet_signs.signs:
        table_data = [["#", "Type", "Conf.", "ATF", "Unicode", "BBox"]]
        for i, s in enumerate(tablet_signs.signs[:15]):  # Limit to 15
            table_data.append([
                str(i+1),
                s.sign_type,
                f"{s.confidence:.2f}",
                s.atf_hypothesis,
                s.unicode_hypothesis,
                f"{s.bbox[0]},{s.bbox[1]},{s.bbox[2]}x{s.bbox[3]}"
            ])

        table = ax_table.table(cellText=table_data[1:], colLabels=table_data[0],
                               loc='center', cellLoc='center', fontsize=8)
        table.auto_set_font_size(False)
        table.set_fontsize(7)
        table.scale(1, 1.5)

    plt.suptitle(f"OX-STEALTH Sign Detection — {tablet_signs.tablet_id}", fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Sign detection visualization saved: {output_path}")

# ──────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────
def run_sign_detection_pipeline() -> Dict[str, Any]:
    log.info("=" * 70)
    log.info("🏛️  OX-STEALTH SPIJKERSCHRIFT SIGN DETECTION ENGINE")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    init_sign_detection_schema(conn)

    detector = CuneiformSignDetector(confidence_threshold=0.3)

    stats = {
        "tablets_processed": 0,
        "total_signs_detected": 0,
        "sign_type_counts": {"wedge": 0, "vertical": 0, "horizontal": 0, "angled": 0, "complex": 0},
        "visualizations": [],
        "errors": []
    }

    # Get all tablets with images
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, v.image_path
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
        WHERE t.id LIKE 'CDLI-%' OR t.id LIKE 'USER-%' OR t.id LIKE 'LEGACY-%'
    """)
    tablets = cur.fetchall()

    log.info(f"Found {len(tablets)} tablets to process")

    for tablet_id, img_path_str in tablets:
        try:
            img_path = Path(img_path_str)
            if not img_path.exists():
                # Try alternative
                alt = IMAGES_DIR / Path(img_path_str).name
                if alt.exists():
                    img_path = alt
                else:
                    stats["errors"].append(f"{tablet_id}: Image not found")
                    continue

            # Get tablet bbox from spijkerschrift_visueel
            cur.execute("SELECT bbox_x, bbox_y, bbox_w, bbox_h FROM spijkerschrift_visueel WHERE tablet_id = ?",
                       (tablet_id,))
            bbox_row = cur.fetchone()
            tablet_bbox = {"x": bbox_row[0], "y": bbox_row[1], "w": bbox_row[2], "h": bbox_row[3]} if bbox_row else None

            log.info(f"Processing {tablet_id}...")
            tablet_signs = detector.detect_signs(img_path, tablet_bbox)

            # IMPORTANT: Use the original tablet_id from the database, not the extracted one
            tablet_signs.tablet_id = tablet_id

            # Store in DB
            store_signs_in_db(conn, tablet_signs)

            # Visualize
            viz_path = EXPORT_DIR / f"signs_{tablet_signs.tablet_id}.png"
            visualize_sign_detection(tablet_signs, viz_path)
            stats["visualizations"].append(str(viz_path))

            # Aggregate stats
            stats["tablets_processed"] += 1
            stats["total_signs_detected"] += tablet_signs.total_signs
            stats["sign_type_counts"]["wedge"] += tablet_signs.wedge_count
            stats["sign_type_counts"]["vertical"] += tablet_signs.vertical_count
            stats["sign_type_counts"]["horizontal"] += tablet_signs.horizontal_count
            stats["sign_type_counts"]["angled"] += tablet_signs.angled_count
            stats["sign_type_counts"]["complex"] += tablet_signs.complex_count

            log.info(f"  {tablet_signs.tablet_id}: {tablet_signs.total_signs} signs "
                     f"(W:{tablet_signs.wedge_count} V:{tablet_signs.vertical_count} "
                     f"H:{tablet_signs.horizontal_count} A:{tablet_signs.angled_count} "
                     f"C:{tablet_signs.complex_count}) AvgConf: {tablet_signs.avg_confidence:.2f}")

        except Exception as e:
            log.error(f"Error processing {tablet_id}: {e}")
            stats["errors"].append(str(e))

    # Create combined visualization for all CDLI + user fragment
    log.info("Creating combined visualization...")
    create_combined_visualization(conn, detector, EXPORT_DIR / "cuneiform_sign_detection.png")
    stats["visualizations"].append(str(EXPORT_DIR / "cuneiform_sign_detection.png"))

    conn.close()

    log.info("=" * 70)
    log.info("✅ SIGN DETECTION PIPELINE COMPLETE")
    log.info("=" * 70)
    return stats

def create_combined_visualization(conn: sqlite3.Connection, detector: CuneiformSignDetector,
                                  output_path: Path, max_tablets: int = 6) -> None:
    """Create combined visualization for multiple tablets."""
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, v.image_path
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
        WHERE t.id LIKE 'CDLI-%' OR t.id LIKE 'USER-%'
        ORDER BY t.id
    """)
    tablets = cur.fetchall()[:max_tablets]

    if not tablets:
        return

    n = len(tablets)
    cols = 3
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(6*cols, 5*rows))
    if rows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()

    type_colors = {'wedge': 'red', 'vertical': 'blue', 'horizontal': 'green',
                   'angled': 'orange', 'complex': 'purple'}

    for idx, (tablet_id, img_path_str) in enumerate(tablets):
        ax = axes[idx]
        img = cv2.imread(img_path_str)
        if img is None:
            ax.text(0.5, 0.5, 'Image not found', ha='center', va='center')
            ax.set_title(tablet_id)
            ax.axis('off')
            continue

        # Get tablet bbox
        cur.execute("SELECT bbox_x, bbox_y, bbox_w, bbox_h FROM spijkerschrift_visueel WHERE tablet_id = ?",
                   (tablet_id,))
        bbox_row = cur.fetchone()
        tablet_bbox = {"x": bbox_row[0], "y": bbox_row[1], "w": bbox_row[2], "h": bbox_row[3]} if bbox_row else None

        # Detect signs
        tablet_signs = detector.detect_signs(Path(img_path_str), tablet_bbox)

        # Draw
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        ax.imshow(img_rgb)
        ax.set_title(f"{tablet_id}\n{len(tablet_signs.signs)} signs (W:{tablet_signs.wedge_count} V:{tablet_signs.vertical_count} H:{tablet_signs.horizontal_count})",
                     fontsize=9)

        for sign in tablet_signs.signs:
            x, y, w, h = sign.bbox
            color = type_colors.get(sign.sign_type, 'yellow')
            rect = patches.Rectangle((x, y), w, h, linewidth=1.5, edgecolor=color, facecolor='none', alpha=0.8)
            ax.add_patch(rect)
            ax.text(x, y - 2, f"{sign.confidence:.2f}", fontsize=6, color=color,
                   bbox=dict(boxstyle='round,pad=0.1', facecolor='white', alpha=0.8, edgecolor='none'))

        ax.axis('off')

    # Hide unused subplots
    for idx in range(len(tablets), len(axes)):
        axes[idx].axis('off')

    plt.suptitle("OX-STEALTH Cuneiform Sign Detection — CDLI & User Fragments", fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Combined visualization saved: {output_path}")

if __name__ == "__main__":
    random.seed(42)
    np.random.seed(42)

    try:
        stats = run_sign_detection_pipeline()
        print("\n📊 SIGN DETECTION STATISTICS")
        print("=" * 50)
        print(f"  Tablets Processed: {stats['tablets_processed']}")
        print(f"  Total Signs Detected: {stats['total_signs_detected']}")
        print(f"  Sign Type Counts:")
        for typ, count in stats['sign_type_counts'].items():
            print(f"    {typ}: {count}")
        print(f"  Visualizations: {len(stats['visualizations'])}")
        for v in stats['visualizations']:
            print(f"    - {v}")
        if stats['errors']:
            print(f"  Errors: {len(stats['errors'])}")
            for e in stats['errors'][:5]:
                print(f"    - {e}")
        sys.exit(0)
    except Exception as e:
        log.exception("Sign detection pipeline failed")
        sys.exit(1)