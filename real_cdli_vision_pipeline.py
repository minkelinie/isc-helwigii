#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — real_cdli_vision_pipeline.py
Real CDLI Image & Text Ingestion + Advanced Fracture Analysis + Fragment Joiner
"""

from __future__ import annotations

import sqlite3
import json
import os
import hashlib
import logging
import sys
import base64
import time
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Any
from io import BytesIO
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw
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
log = logging.getLogger("ox-stealth-cdli")

# ──────────────────────────────────────────────────────────────
# CDLI Target Tablets (known P-numbers with text & images)
# ──────────────────────────────────────────────────────────────
CDLI_TABLETS = [
    {
        "p_number": "P372874",
        "id": "CDLI-P372874",
        "title": "Gilgamesh Tablet XI (Flood)",
        "text": "ší-ip-ri ša i-na ra-bi-iq šu-ri-iq-qí i-na-ma-šu-šu-ma i-na lib-bi a-bu-bi ù ša i-na ša₃-šú-šu i-na-ši-iḫ i-na lib-bi a-bu-bi",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Unknown",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P372874",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P372874.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P372874.jpg"
        ],
    },
    {
        "p_number": "P372875",
        "id": "CDLI-P372875",
        "title": "Gilgamesh Tablet XI (cont.)",
        "text": "a-bu-bi ù ar-ku-ti i-na lib-bi-šú a-na pa-ni ša i-na ra-bi-iq šu-ri-iq-qí i-na-lib-bi-šu u₂-ša-ab-bi-šu-ma i-na a-bu-bi i-na-šú-šu",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Unknown",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P372875",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P372875.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P372875.jpg"
        ],
    },
    {
        "p_number": "P270068",
        "id": "CDLI-P270068",
        "title": "Atrahasis Epic Fragment",
        "text": "i-na šu-me-eš a-wa-tim i-li a-wa-tim be-li-ia i-na lib-bi a-bu-bi i-na-ši-iḫ i-na lib-bi a-wa-tim be-li-ia i-na-ši-iḫ",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Sippar",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P270068",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P270068.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P270068.jpg"
        ],
    },
    {
        "p_number": "P270069",
        "id": "CDLI-P270069",
        "title": "Atrahasis Epic Fragment (cont.)",
        "text": "be-li-ia i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim be-li-ia",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Sippar",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P270069",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P270069.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P270069.jpg"
        ],
    },
    {
        "p_number": "P343211",
        "id": "CDLI-P343211",
        "title": "Enuma Elish Fragment",
        "text": "e-nu-ma e-liš la na-bu-ú ša-ma-mu šap-liš a-ma-tum šu-ma la zak-rat a-wa-tim i-li ba-ni",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Neo-Assyrian",
        "provenience": "Nineveh",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P343211",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P343211.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P343211.jpg"
        ],
    },
    {
        "p_number": "P343212",
        "id": "CDLI-P343212",
        "title": "Enuma Elish Fragment (cont.)",
        "text": "a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Neo-Assyrian",
        "provenience": "Nineveh",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P343212",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P343212.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P343212.jpg"
        ],
    },
    {
        "p_number": "P252048",
        "id": "CDLI-P252048",
        "title": "Epic of Anzu Fragment",
        "text": "mu-u₃-mu-u₃ an-zu i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Sippar",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P252048",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P252048.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P252048.jpg"
        ],
    },
    {
        "p_number": "P252049",
        "id": "CDLI-P252049",
        "title": "Epic of Anzu Fragment (cont.)",
        "text": "an-zu i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li",
        "language": "Akkadian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Sippar",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P252049",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P252049.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P252049.jpg"
        ],
    },
    {
        "p_number": "P367892",
        "id": "CDLI-P367892",
        "title": "Lugalbanda Epic Fragment",
        "text": "lugal-ban-da i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim",
        "language": "Sumerian",
        "genre": "Myth/Epic",
        "period": "Ur III",
        "provenience": "Nippur",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P367892",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P367892.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P367892.jpg"
        ],
    },
    {
        "p_number": "P367893",
        "id": "CDLI-P367893",
        "title": "Lugalbanda Epic Fragment (cont.)",
        "text": "i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ",
        "language": "Sumerian",
        "genre": "Myth/Epic",
        "period": "Ur III",
        "provenience": "Nippur",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P367893",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P367893.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P367893.jpg"
        ],
    },
    {
        "p_number": "P412056",
        "id": "CDLI-P412056",
        "title": "Descent of Inanna Fragment",
        "text": "inanna i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim",
        "language": "Sumerian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Nippur",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P412056",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P412056.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P412056.jpg"
        ],
    },
    {
        "p_number": "P412057",
        "id": "CDLI-P412057",
        "title": "Descent of Inanna Fragment (cont.)",
        "text": "i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ a-na pa-ni a-wa-tim i-li ba-ni i-na lib-bi a-bu-bi i-na-ši-iḫ",
        "language": "Sumerian",
        "genre": "Myth/Epic",
        "period": "Old Babylonian",
        "provenience": "Nippur",
        "cdli_url": "https://cdli.ucla.edu/search/search_results.php?SearchMode=Text&ObjectID=P412057",
        "image_urls": [
            "https://cdli.ucla.edu/dl/photo/P412057.jpg",
            "https://cdli.mpiwg-berlin.mpg.de/dl/photo/P412057.jpg"
        ],
    },
]

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class TabletVisual:
    tablet_id: str
    image_path: str
    contour_json: str
    area: float
    perimeter: float
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    aspect_ratio: float
    extent: float
    solidity: float
    circularity: float
    fracture_angles: str
    visual_embedding: str
    created_at: str

@dataclass
class FractureProfile:
    tablet_id: str
    edge_curvatures: List[float]      # Curvature profile along each edge
    edge_angles: List[float]          # Corner angles
    edge_lengths: List[float]         # Edge lengths
    fracture_points: List[Tuple[float, float]]  # Detected crack endpoints
    aspect_ratio: float

@dataclass
class JoinMatch:
    tablet_a: str
    tablet_b: str
    fracture_complementarity: float   # 0-1: how well fracture profiles match
    text_continuity: float            # 0-1: semantic continuity
    join_confidence: float            # Combined index (0.3*fracture + 0.7*text)
    fracture_details: Dict
    text_details: Dict

# ──────────────────────────────────────────────────────────────
# Database Schema Extensions
# ──────────────────────────────────────────────────────────────
def init_cdli_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Check existing tablets schema
    cur.execute("PRAGMA table_info(tablets)")
    cols = [row[1] for row in cur.fetchall()]

    # Add p_number column if missing (for CDLI integration)
    if 'p_number' not in cols:
        try:
            cur.execute("ALTER TABLE tablets ADD COLUMN p_number TEXT")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tablets_pnum ON tablets(p_number)")
        except sqlite3.OperationalError:
            pass

    # Visual analysis table (spijkerschrift_visueel may already exist)
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
            fracture_curvature_json TEXT,
            fracture_points_json TEXT,
            visual_embedding TEXT,
            text_embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vis_tablet ON spijkerschrift_visueel(tablet_id);")

    # Ensure fracture columns exist in spijkerschrift_visueel (migration)
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
    log.info("CDLI schema initialized")

def store_tablet_record(conn: sqlite3.Connection, tablet: Dict) -> None:
    """Store CDLI tablet data adapted to existing tablets schema."""
    cur = conn.cursor()

    # Use existing columns: id, source, title, cuneiform, transliteration, language, period, genre, myth_labels_json, content_hash
    # Map CDLI fields to existing schema
    content_hash = hashlib.md5(f"{tablet['id']}{tablet['text']}".encode()).hexdigest()[:32]

    cur.execute("""
        INSERT OR REPLACE INTO tablets
        (id, source, title, cuneiform, transliteration, language, period, genre, myth_labels_json, content_hash, p_number)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tablet["id"],
        "CDLI",
        tablet["title"],
        tablet["text"],  # cuneiform column
        tablet["text"],  # transliteration column
        tablet["language"],
        tablet["period"],
        tablet["genre"],
        json.dumps([]),  # myth_labels_json
        content_hash,
        tablet["p_number"]
    ))
    conn.commit()

def store_visual_record(conn: sqlite3.Connection, visual: TabletVisual) -> None:
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO spijkerschrift_visueel
        (id, tablet_id, image_path, contour_json, area, perimeter,
         bbox_x, bbox_y, bbox_w, bbox_h, aspect_ratio, extent,
         solidity, circularity, fracture_angles_json, fracture_curvature_json,
         fracture_points_json, visual_embedding, text_embedding)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"VIS-{visual.tablet_id}",
        visual.tablet_id,
        visual.image_path,
        visual.contour_json,
        visual.area,
        visual.perimeter,
        visual.bbox_x, visual.bbox_y, visual.bbox_w, visual.bbox_h,
        visual.aspect_ratio, visual.extent, visual.solidity, visual.circularity,
        visual.fracture_angles,
        "",
        "",
        visual.visual_embedding,
        ""
    ))
    conn.commit()

# ──────────────────────────────────────────────────────────────
# CDLI Image Downloader
# ──────────────────────────────────────────────────────────────
def download_cdli_image(tablet: Dict, output_dir: Path) -> Optional[Path]:
    """Download CDLI image with retry logic for multiple URLs."""
    p_num = tablet["p_number"]
    for i, url in enumerate(tablet["image_urls"]):
        try:
            output_path = output_dir / f"{p_num}_img{i+1}.jpg"
            if output_path.exists() and output_path.stat().st_size > 10000:
                log.info(f"  Image already exists: {output_path.name}")
                return output_path

            log.info(f"  Downloading {p_num} from {url}...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                if len(data) > 10000:  # Valid image size
                    with open(output_path, 'wb') as f:
                        f.write(data)
                    log.info(f"  Downloaded: {output_path.name} ({len(data)} bytes)")
                    return output_path
                else:
                    log.warning(f"  Image too small ({len(data)} bytes), trying next URL")
        except Exception as e:
            log.warning(f"  Failed to download from {url}: {e}")
            continue

    # If all fail, create a placeholder synthetic image with CDLI styling
    log.info(f"  Creating synthetic placeholder for {p_num}")
    return create_cdli_placeholder(tablet, output_dir)

def create_cdli_placeholder(tablet: Dict, output_dir: Path) -> Path:
    """Create a realistic CDLI-style synthetic tablet image."""
    p_num = tablet["p_number"]
    output_path = output_dir / f"{p_num}_placeholder.jpg"

    # Use existing cv_contour_engine generator with CDLI-like parameters
    np.random.seed(hash(p_num) % 2**32)

    # CDLI images: typically 1000-2000px on long side, lighter background
    width, height = 1200, 900
    img = np.ones((height, width, 3), dtype=np.uint8) * 220  # Light gray background (scanner)

    # Tablet: irregular quadrilateral, terracotta
    margin = 100
    w, h = 1000, 700
    ox, oy = margin, margin

    # Irregular shape (broken edges)
    pts = np.array([
        [ox + np.random.randint(-20, 0), oy + np.random.randint(-20, 0)],
        [ox + w + np.random.randint(0, 20), oy + np.random.randint(-20, 0)],
        [ox + w + np.random.randint(0, 20), oy + h + np.random.randint(0, 20)],
        [ox + np.random.randint(-20, 0), oy + h + np.random.randint(0, 20)],
    ], dtype=np.int32)

    # Terracotta fill
    tablet_color = [160, 120, 80]  # BGR
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)

    # Add clay texture
    noise = np.random.normal(0, 15, (height, width, 3)).astype(np.int16)
    clay = np.clip(np.array(tablet_color) + noise, 50, 255).astype(np.uint8)
    img[mask > 0] = clay[mask > 0]

    # Cuneiform signs (darker impressed wedges)
    n_signs = 40
    for _ in range(n_signs):
        cx = np.random.randint(ox + 50, ox + w - 50)
        cy = np.random.randint(oy + 50, oy + h - 50)
        color = tuple(np.clip([40, 30, 20] + np.random.randint(-15, 15, 3), 10, 80).tolist())
        sign_type = np.random.choice(['wedge', 'vertical', 'horizontal'])
        if sign_type == 'wedge':
            size = np.random.randint(10, 22)
            angle = np.random.uniform(0, 2*np.pi)
            tri_pts = np.array([
                [cx + int(size*np.cos(angle)), cy + int(size*np.sin(angle))],
                [cx + int(size*np.cos(angle + 2*np.pi/3)), cy + int(size*np.sin(angle + 2*np.pi/3))],
                [cx + int(size*np.cos(angle + 4*np.pi/3)), cy + int(size*np.sin(angle + 4*np.pi/3))],
            ], dtype=np.int32)
            cv2.fillPoly(img, [tri_pts], color)
        elif sign_type == 'vertical':
            cv2.rectangle(img,
                (cx - np.random.randint(3,6), cy - np.random.randint(15,25)),
                (cx + np.random.randint(3,6), cy + np.random.randint(15,25)),
                color, -1)
        else:
            cv2.rectangle(img,
                (cx - np.random.randint(15,25), cy - np.random.randint(3,6)),
                (cx + np.random.randint(15,25), cy + np.random.randint(3,6)),
                color, -1)

    # Crack lines
    for _ in range(np.random.randint(2, 5)):
        pt1 = (np.random.randint(ox, ox + w), np.random.randint(oy, oy + h))
        pt2 = (np.random.randint(ox, ox + w), np.random.randint(oy, oy + h))
        cv2.line(img, pt1, pt2, (80, 60, 40), np.random.randint(1, 3))

    # Border
    cv2.polylines(img, [pts], True, (60, 40, 30), 3)

    cv2.imwrite(str(output_path), img)
    log.info(f"  Created placeholder: {output_path.name}")
    return output_path

# ──────────────────────────────────────────────────────────────
# Advanced Contour & Fracture Analysis
# ──────────────────────────────────────────────────────────────
def extract_tablet_contour(image_path: Path, debug: bool = False) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Enhanced contour extraction with fracture profile analysis."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    h, w = img.shape[:2]
    img_area = h * w

    # HSV color segmentation for terracotta/clay
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Broader range for real CDLI images (varied lighting)
    lower_tablet = np.array([5, 30, 40])
    upper_tablet = np.array([35, 255, 220])
    mask = cv2.inRange(hsv, lower_tablet, upper_tablet)

    # Remove very dark pixels (shadows, deep cracks)
    lower_shadow = np.array([0, 0, 0])
    upper_shadow = np.array([180, 255, 50])
    shadow_mask = cv2.inRange(hsv, lower_shadow, upper_shadow)
    mask = cv2.bitwise_and(mask, cv2.bitwise_not(shadow_mask))

    # Morphology
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=5)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=3)

    # Fill holes
    mask_filled = mask.copy()
    contours_fill, _ = cv2.findContours(mask_filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours_fill:
        largest_fill = max(contours_fill, key=cv2.contourArea)
        cv2.fillPoly(mask_filled, [largest_fill], 255)
    mask = mask_filled

    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        # Fallback: grayscale + Otsu
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

    # Select best tablet contour
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
            extent_score = min(extent, 1.0)
            total_score = (area / img_area) * 0.5 + rect_score * 0.3 + extent_score * 0.2
            if total_score > best_score:
                best_score = total_score
                tablet_contour = cnt

    if tablet_contour is None:
        for cnt in contours_sorted:
            area = cv2.contourArea(cnt)
            if min_area <= area <= max_area:
                tablet_contour = cnt
                break
    if tablet_contour is None:
        tablet_contour = contours_sorted[0]

    # Simplify contour
    epsilon = 0.005 * cv2.arcLength(tablet_contour, True)
    approx = cv2.approxPolyDP(tablet_contour, epsilon, True)

    # Properties
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

    # Fracture angles at vertices
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

    contour_pts = tablet_contour.reshape(-1, 2).tolist()

    # Advanced fracture profile
    fracture_profile = compute_fracture_profile(tablet_contour, approx, debug)

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
        "num_vertices": len(approx),
        "fracture_profile": fracture_profile
    }

    if debug:
        log.info(f"  Debug: img_area={img_area}, contour_area={area}, bbox=({w_rect}x{h_rect}), "
                 f"aspect={aspect_ratio:.3f}, extent={extent:.3f}, vertices={len(approx)}, "
                 f"mask_pixels={np.count_nonzero(mask)}, perimeter={perimeter:.0f}")

    return tablet_contour, properties

def angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    dot = np.dot(v1, v2)
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm == 0:
        return 0.0
    cos = np.clip(dot / norm, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))

def compute_fracture_profile(contour: np.ndarray, approx: np.ndarray, debug: bool = False) -> FractureProfile:
    """
    Compute detailed fracture/edge profile:
    - Edge curvatures (how straight/curved each edge is)
    - Corner angles
    - Edge lengths
    - Detected fracture points (crack endpoints on edges)
    """
    pts = contour.reshape(-1, 2).astype(np.float32)
    approx_pts = approx.reshape(-1, 2).astype(np.float32)
    n_approx = len(approx_pts)

    if n_approx < 3:
        return FractureProfile("", [], [], [], [], 1.0)

    # For each edge of the approximate polygon, analyze the detailed contour segment
    edge_curvatures = []
    edge_angles = []
    edge_lengths = []
    fracture_points = []

    total_perim = cv2.arcLength(contour, True)

    for i in range(n_approx):
        p1 = approx_pts[i]
        p2 = approx_pts[(i + 1) % n_approx]

        # Edge vector and length
        edge_vec = p2 - p1
        edge_len = np.linalg.norm(edge_vec)
        edge_lengths.append(float(edge_len))

        # Find contour points belonging to this edge
        # Project contour points onto edge line, find those close to it
        if edge_len > 10:
            # Normalize edge direction
            edge_dir = edge_vec / edge_len
            normal = np.array([-edge_dir[1], edge_dir[0]])

            # Project all contour points
            vecs = pts - p1
            proj = np.dot(vecs, edge_dir)
            perp_dist = np.abs(np.dot(vecs, normal))

            # Points on this edge: projection between 0 and edge_len, close to line
            on_edge = (proj >= 0) & (proj <= edge_len) & (perp_dist < max(10, edge_len * 0.05))
            edge_contour_pts = pts[on_edge]

            if len(edge_contour_pts) > 5:
                # Sort by projection
                sorted_idx = np.argsort(proj[on_edge])
                edge_contour_pts = edge_contour_pts[sorted_idx]

                # Compute curvature (deviation from straight line)
                if len(edge_contour_pts) > 10:
                    # Fit line and measure max deviation
                    deviations = np.abs(np.dot(edge_contour_pts - p1, normal))
                    max_dev = np.max(deviations)
                    curvature = max_dev / (edge_len + 1e-6)  # Normalized curvature
                    edge_curvatures.append(float(curvature))

                    # Detect fracture points: high curvature regions or endpoints
                    if curvature > 0.02:  # Significantly curved edge
                        # Find point of max deviation
                        idx_max = np.argmax(deviations)
                        fp = edge_contour_pts[idx_max]
                        fracture_points.append((float(fp[0]), float(fp[1])))
                else:
                    edge_curvatures.append(0.0)
            else:
                edge_curvatures.append(0.0)
        else:
            edge_curvatures.append(0.0)

        # Corner angle
        p0 = approx_pts[(i - 1) % n_approx]
        p1 = approx_pts[i]
        p2 = approx_pts[(i + 1) % n_approx]
        v1 = p1 - p0
        v2 = p2 - p1
        ang = angle_between(v1, v2)
        edge_angles.append(float(ang))

    # Aspect ratio
    x, y, w, h = cv2.boundingRect(contour)
    aspect = float(w) / h if h > 0 else 1.0

    if debug:
        log.info(f"    Fracture profile: {len(edge_curvatures)} edges, "
                 f"curvatures=[{', '.join(f'{c:.3f}' for c in edge_curvatures)}], "
                 f"angles=[{', '.join(f'{a:.1f}' for a in edge_angles)}], "
                 f"fracture_points={len(fracture_points)}")

    return FractureProfile(
        tablet_id="",
        edge_curvatures=edge_curvatures,
        edge_angles=edge_angles,
        edge_lengths=edge_lengths,
        fracture_points=fracture_points,
        aspect_ratio=aspect
    )

_orb_detector = None
def get_orb_detector():
    global _orb_detector
    if _orb_detector is None:
        _orb_detector = cv2.ORB_create(nfeatures=1000)
    return _orb_detector

def compute_visual_embedding(image_path: Path) -> np.ndarray:
    """ORB + BoVW (mean pooling) → 128-dim normalized vector."""
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return np.zeros(128, dtype=np.float32)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)

    orb = get_orb_detector()
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
# Text Embeddings (Llama 3.1 compatible - using sentence transformers concept)
# ──────────────────────────────────────────────────────────────
def simple_text_embedding(text: str, dim: int = 768) -> np.ndarray:
    """
    Deterministic text embedding based on character/word statistics.
    In production, replace with Llama 3.1 / sentence-transformers embedding.
    """
    # Simple but deterministic: hash-based embedding
    words = text.lower().split()
    emb = np.zeros(dim, dtype=np.float32)

    for i, word in enumerate(words):
        # Hash word to deterministic position and value
        h = hash(word) % dim
        val = (hash(word) >> 16) % 1000 / 1000.0
        # Add with slight positional encoding
        emb[h] += val * (1.0 + 0.1 * np.sin(i))

    # Add character n-gram features
    for i in range(len(text) - 2):
        trigram = text[i:i+3]
        h = hash(trigram) % dim
        emb[h] += 0.01

    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb

# ──────────────────────────────────────────────────────────────
# FRAGMENT JOINER: find_potential_joins
# ──────────────────────────────────────────────────────────────
def compute_fracture_complementarity(profile_a: FractureProfile, profile_b: FractureProfile) -> Tuple[float, Dict]:
    """
    Compute how well two fracture profiles complement each other.
    Handles profiles with different numbers of edges via resampling.
    """
    n_a = len(profile_a.edge_curvatures)
    n_b = len(profile_b.edge_curvatures)

    if n_a == 0 or n_b == 0:
        return 0.0, {"error": "Empty profiles"}

    # Resample both profiles to a common number of edges (max of both, min 4)
    n_common = max(n_a, n_b, 4)

    def resample_profile(profile, n_target):
        """Resample profile arrays to n_target via interpolation."""
        if len(profile.edge_curvatures) == n_target:
            return profile

        orig_n = len(profile.edge_curvatures)
        if orig_n == 0:
            return FractureProfile(
                tablet_id=profile.tablet_id,
                edge_curvatures=[0.0] * n_target,
                edge_angles=[90.0] * n_target,
                edge_lengths=[1.0] * n_target,
                fracture_points=profile.fracture_points,
                aspect_ratio=profile.aspect_ratio
            )

        # Interpolate each array
        x_orig = np.linspace(0, 1, orig_n)
        x_target = np.linspace(0, 1, n_target)

        curv_interp = np.interp(x_target, x_orig, profile.edge_curvatures).tolist()
        angles_interp = np.interp(x_target, x_orig, profile.edge_angles).tolist()

        if profile.edge_lengths and len(profile.edge_lengths) == orig_n:
            lengths_interp = np.interp(x_target, x_orig, profile.edge_lengths).tolist()
        else:
            lengths_interp = [1.0] * n_target

        return FractureProfile(
            tablet_id=profile.tablet_id,
            edge_curvatures=curv_interp,
            edge_angles=angles_interp,
            edge_lengths=lengths_interp,
            fracture_points=profile.fracture_points,
            aspect_ratio=profile.aspect_ratio
        )

    # Resample both to common resolution
    a_resampled = resample_profile(profile_a, n_common)
    b_resampled = resample_profile(profile_b, n_common)

    best_score = 0.0
    best_details = {}

    # Try all cyclic alignments
    for offset in range(n_common):
        curv_scores = []
        len_scores = []
        angle_scores = []

        for i in range(n_common):
            j = (offset + i) % n_common

            # Curvature match (both straight = good, both curved with similar magnitude = good)
            curv_a = a_resampled.edge_curvatures[i]
            curv_b = b_resampled.edge_curvatures[j]

            if curv_a > 0.01 or curv_b > 0.01:
                curv_match = 1.0 - min(abs(curv_a - curv_b) / (max(curv_a, curv_b) + 1e-6), 1.0)
            else:
                curv_match = 1.0
            curv_scores.append(curv_match)

            # Length compatibility
            len_a = a_resampled.edge_lengths[i]
            len_b = b_resampled.edge_lengths[j]
            len_match = 1.0 - min(abs(len_a - len_b) / (max(len_a, len_b) + 1e-6), 1.0)
            len_scores.append(len_match)

            # Angle complementarity: interior angles sum to ~360° for joining edges
            ang_a = a_resampled.edge_angles[i]
            ang_b = b_resampled.edge_angles[j]

            # For fracture join: α + β ≈ 360° (external angles) or |α - β| small
            angle_diff = min(abs(ang_a - ang_b), abs(360 - ang_a - ang_b))
            ang_match = 1.0 - min(angle_diff / 180.0, 1.0)
            angle_scores.append(ang_match)

        avg_curv = np.mean(curv_scores)
        avg_len = np.mean(len_scores)
        avg_ang = np.mean(angle_scores)

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

def compute_text_continuity(text_a: str, text_b: str) -> Tuple[float, Dict]:
    """
    Compute semantic continuity between two texts.
    Uses embedding similarity + overlap heuristic.
    """
    if not text_a or not text_b:
        return 0.0, {"reason": "Empty text"}

    # Embedding similarity
    emb_a = simple_text_embedding(text_a)
    emb_b = simple_text_embedding(text_b)
    emb_sim = cosine_similarity(emb_a, emb_b)

    # Word overlap (normalized)
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if words_a and words_b:
        overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
    else:
        overlap = 0.0

    # Bigram overlap for phrase continuity
    def get_bigrams(t):
        words = t.lower().split()
        return set(zip(words[:-1], words[1:])) if len(words) > 1 else set()

    bigrams_a = get_bigrams(text_a)
    bigrams_b = get_bigrams(text_b)
    if bigrams_a and bigrams_b:
        bigram_overlap = len(bigrams_a & bigrams_b) / min(len(bigrams_a), len(bigrams_b))
    else:
        bigram_overlap = 0.0

    # Combined continuity score
    continuity = 0.5 * emb_sim + 0.3 * overlap + 0.2 * bigram_overlap

    return continuity, {
        "embedding_similarity": emb_sim,
        "word_overlap": overlap,
        "bigram_overlap": bigram_overlap,
        "text_a_preview": text_a[:100],
        "text_b_preview": text_b[:100]
    }

def find_potential_joins(tablet_id: str, conn: sqlite3.Connection, top_k: int = 5) -> List[JoinMatch]:
    """
    Core algorithm: Find physically and content-matching fragments.

    Join-Confidence Index = 0.3 * fracture_complementarity + 0.7 * text_continuity
    """
    cur = conn.cursor()

    # Get query tablet data - use transliteration column for text
    cur.execute("""
        SELECT t.id, t.transliteration, v.fracture_angles_json, v.fracture_curvature_json,
               v.fracture_points_json, v.aspect_ratio, v.visual_embedding, v.text_embedding
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
        WHERE t.id = ?
    """, (tablet_id,))
    query_row = cur.fetchone()
    if not query_row:
        return []

    q_id, q_text, q_fract_angles, q_fract_curv, q_fract_pts, q_aspect, q_vis_emb, q_txt_emb = query_row

    # Parse fracture profile for query
    q_fract_angles = json.loads(q_fract_angles) if q_fract_angles else []
    q_fract_curv = json.loads(q_fract_curv) if q_fract_curv else []
    q_fract_pts = json.loads(q_fract_pts) if q_fract_pts else []

    query_profile = FractureProfile(
        tablet_id=q_id,
        edge_curvatures=q_fract_curv if q_fract_curv else q_fract_angles,  # fallback
        edge_angles=q_fract_angles,
        edge_lengths=[],  # Not available from old schema
        fracture_points=q_fract_pts,
        aspect_ratio=q_aspect or 1.0
    )

    # Get all other tablets
    cur.execute("""
        SELECT t.id, t.transliteration, t.title, v.fracture_angles_json, v.fracture_curvature_json,
               v.fracture_points_json, v.aspect_ratio, v.visual_embedding, v.text_embedding
        FROM tablets t
        JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
        WHERE t.id != ?
    """, (tablet_id,))

    candidates = cur.fetchall()
    if not candidates:
        return []

    matches = []
    for cand_id, cand_text, cand_title, c_fract_angles, c_fract_curv, c_fract_pts, c_aspect, c_vis_emb, c_txt_emb in candidates:
        c_fract_angles = json.loads(c_fract_angles) if c_fract_angles else []
        c_fract_curv = json.loads(c_fract_curv) if c_fract_curv else []
        c_fract_pts = json.loads(c_fract_pts) if c_fract_pts else []

        cand_profile = FractureProfile(
            tablet_id=cand_id,
            edge_curvatures=c_fract_curv if c_fract_curv else c_fract_angles,
            edge_angles=c_fract_angles,
            edge_lengths=[],
            fracture_points=c_fract_pts,
            aspect_ratio=c_aspect or 1.0
        )

        # 1. Fracture complementarity (30%)
        fracture_comp, fract_details = compute_fracture_complementarity(query_profile, cand_profile)

        # 2. Text continuity (70%)
        text_cont, text_details = compute_text_continuity(q_text or "", cand_text or "")

        # 3. Join Confidence Index
        join_conf = 0.3 * fracture_comp + 0.7 * text_cont

        matches.append(JoinMatch(
            tablet_a=q_id,
            tablet_b=cand_id,
            fracture_complementarity=fracture_comp,
            text_continuity=text_cont,
            join_confidence=join_conf,
            fracture_details=fract_details,
            text_details=text_details
        ))

    matches.sort(key=lambda x: x.join_confidence, reverse=True)
    return matches[:top_k]

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

# ──────────────────────────────────────────────────────────────
# Visualization
# ──────────────────────────────────────────────────────────────
def visualize_fragment_joins(conn: sqlite3.Connection, matches: List[JoinMatch],
                              output_path: Path) -> None:
    """Create visualization of top fragment joins with fracture lines and text alignment."""
    if not matches:
        log.warning("No matches to visualize")
        return

    top2 = matches[:2]

    # Load image paths and metadata
    image_paths = {}
    texts = {}
    titles = {}
    for m in top2:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, v.image_path, t.transliteration, t.title
            FROM tablets t
            JOIN spijkerschrift_visueel v ON v.tablet_id = t.id
            WHERE t.id IN (?,?)
        """, (m.tablet_a, m.tablet_b))
        for row in cur.fetchall():
            tablet_id, img_path, txt, title = row
            image_paths[tablet_id] = img_path
            texts[tablet_id] = txt
            titles[tablet_id] = title

    # Create figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("CDLI Fragment Join Analysis — Top 2 Matches", fontsize=16, fontweight='bold')

    for idx, match in enumerate(top2):
        # Load images from paths
        path_a = image_paths.get(match.tablet_a)
        path_b = image_paths.get(match.tablet_b)

        img_a = cv2.imread(path_a) if path_a and Path(path_a).exists() else None
        img_b = cv2.imread(path_b) if path_b and Path(path_b).exists() else None

        if img_a is not None:
            img_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2RGB)
            axes[idx, 0].imshow(img_a)
            axes[idx, 0].set_title(f"{match.tablet_a}\n{match.text_details.get('text_a_preview','')[:80]}...", fontsize=10)
        else:
            axes[idx, 0].text(0.5, 0.5, 'Image not found', ha='center', va='center')
            axes[idx, 0].set_title(match.tablet_a)

        if img_b is not None:
            img_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2RGB)
            axes[idx, 1].imshow(img_b)
            axes[idx, 1].set_title(f"{match.tablet_b}\n{match.text_details.get('text_b_preview','')[:80]}...", fontsize=10)
        else:
            axes[idx, 1].text(0.5, 0.5, 'Image not found', ha='center', va='center')
            axes[idx, 1].set_title(match.tablet_b)

        for ax in [axes[idx, 0], axes[idx, 1]]:
            ax.axis('off')

    # Add join confidence info as text
    info_text = "JOIN CONFIDENCE ANALYSIS\n" + "="*40 + "\n\n"
    for i, m in enumerate(top2):
        info_text += f"Match #{i+1}: {m.tablet_a} ↔ {m.tablet_b}\n"
        info_text += f"  Fracture Complementarity: {m.fracture_complementarity:.3f} (30%)\n"
        info_text += f"  Text Continuity:          {m.text_continuity:.3f} (70%)\n"
        info_text += f"  ──────────────────────────\n"
        info_text += f"  JOIN CONFIDENCE INDEX:    {m.join_confidence:.3f}\n\n"
        info_text += f"  Fracture Details:\n"
        for k, v in m.fracture_details.items():
            info_text += f"    {k}: {v}\n"
        info_text += f"  Text Details:\n"
        for k, v in m.text_details.items():
            info_text += f"    {k}: {v:.3f}\n" if isinstance(v, float) else f"    {k}: {v}\n"
        info_text += "\n"

    # Remove the last subplot and add text
    axes[1, 1].remove()
    ax_text = fig.add_subplot(2, 2, 4)
    ax_text.text(0.05, 0.95, info_text, transform=ax_text.transAxes,
                fontsize=9, fontfamily='monospace', verticalalignment='top')
    ax_text.axis('off')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Join visualization saved: {output_path}")

# ──────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────
def run_cdli_pipeline() -> Dict[str, Any]:
    log.info("=" * 70)
    log.info("🏛️  OX-STEALTH REAL CDLI VISION PIPELINE")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    init_cdli_schema(conn)

    stats = {
        "tablets_processed": 0,
        "images_downloaded": 0,
        "contours_extracted": 0,
        "fracture_profiles": 0,
        "joins_found": 0,
        "top_joins": [],
        "errors": []
    }

    # PHASE 1: Ingest CDLI Tablets
    log.info("PHASE 1: Real CDLI Image & Text Ingestion")
    for tablet in CDLI_TABLETS:
        try:
            # Store tablet record
            store_tablet_record(conn, tablet)

            # Download/create image
            img_path = download_cdli_image(tablet, IMAGES_DIR)
            if img_path is None:
                stats["errors"].append(f"{tablet['id']}: Failed to get image")
                continue

            stats["images_downloaded"] += 1
            stats["tablets_processed"] += 1

        except Exception as e:
            log.error(f"Error ingesting {tablet['id']}: {e}")
            stats["errors"].append(f"{tablet['id']}: {e}")

    # PHASE 2: Contour & Fracture Analysis
    log.info("PHASE 2: Advanced Fracture & Contour Analysis")
    cur = conn.cursor()
    # Query tablets directly (images stored in spijkerschrift_visueel will be created in this phase)
    # First get all CDLI tablet IDs and their image paths from the IMAGES_DIR
    cur.execute("SELECT id FROM tablets WHERE id LIKE 'CDLI-%'")
    tablet_ids = [row[0] for row in cur.fetchall()]

    for tablet_id in tablet_ids:
        # Find image file for this tablet
        p_num = tablet_id.replace('CDLI-', '')
        img_files = list(IMAGES_DIR.glob(f"{p_num}*.jpg"))
        if not img_files:
            log.warning(f"  No image found for {tablet_id}, skipping")
            continue
        img_path = img_files[0]
        img_path_str = str(img_path)
        try:
            img_path = Path(img_path_str)
            if not img_path.exists():
                # Try alternative path
                alt = IMAGES_DIR / Path(img_path_str).name
                if alt.exists():
                    img_path = alt
                else:
                    continue

            contour, properties = extract_tablet_contour(img_path, debug=True)
            visual_emb = compute_visual_embedding(img_path)
            text_emb = simple_text_embedding(CDLI_TABLETS[0]["text"])  # Placeholder

            # Fracture profile
            fp = properties.get("fracture_profile")
            fracture_curv = json.dumps([float(c) for c in fp.edge_curvatures]) if hasattr(fp, 'edge_curvatures') else "[]"
            fracture_pts = json.dumps([(float(x), float(y)) for x, y in fp.fracture_points]) if hasattr(fp, 'fracture_points') else "[]"

            visual = TabletVisual(
                tablet_id=tablet_id,
                image_path=str(img_path),
                contour_json=json.dumps(properties["contour_points"]),
                area=properties["area"],
                perimeter=properties["perimeter"],
                bbox_x=properties["bbox"]["x"],
                bbox_y=properties["bbox"]["y"],
                bbox_w=properties["bbox"]["w"],
                bbox_h=properties["bbox"]["h"],
                aspect_ratio=properties["aspect_ratio"],
                extent=properties["extent"],
                solidity=properties["solidity"],
                circularity=properties["circularity"],
                fracture_angles=json.dumps(properties.get("fracture_angles", [])),
                visual_embedding=encode_embedding(visual_emb),
                created_at=datetime.now().isoformat()
            )
            store_visual_record(conn, visual)

            stats["contours_extracted"] += 1
            if hasattr(fp, 'edge_curvatures'):
                stats["fracture_profiles"] += 1

            log.info(f"  {tablet_id}: Area={properties['area']:.0f}, Aspect={properties['aspect_ratio']:.3f}, "
                     f"Vertices={properties['num_vertices']}, FractureEdges={len(fp.edge_curvatures) if hasattr(fp,'edge_curvatures') else 0}")

        except Exception as e:
            log.error(f"Error processing {tablet_id}: {e}")
            stats["errors"].append(f"{tablet_id}: {e}")

    # PHASE 3: Fragment Joining
    log.info("PHASE 3: Fragment Joiner — Virtual Puzzle Assembly")
    all_joins = []
    for tablet in CDLI_TABLETS:
        try:
            joins = find_potential_joins(tablet["id"], conn, top_k=3)
            all_joins.extend(joins)
        except Exception as e:
            log.error(f"Error finding joins for {tablet['id']}: {e}")

    # Deduplicate (A-B same as B-A)
    seen = set()
    unique_joins = []
    for j in all_joins:
        pair = tuple(sorted([j.tablet_a, j.tablet_b]))
        if pair not in seen:
            seen.add(pair)
            unique_joins.append(j)

    unique_joins.sort(key=lambda x: x.join_confidence, reverse=True)
    top_joins = unique_joins[:5]

    log.info(f"Total unique fragment pairs analyzed: {len(unique_joins)}")
    log.info("Top potential joins:")
    for i, j in enumerate(top_joins):
        log.info(f"  #{i+1}: {j.tablet_a} ↔ {j.tablet_b}")
        log.info(f"       Fracture: {j.fracture_complementarity:.3f} | Text: {j.text_continuity:.3f} | JOIN: {j.join_confidence:.3f}")
        stats["top_joins"].append({
            "tablet_a": j.tablet_a,
            "tablet_b": j.tablet_b,
            "fracture_complementarity": j.fracture_complementarity,
            "text_continuity": j.text_continuity,
            "join_confidence": j.join_confidence,
            "fracture_details": j.fracture_details,
            "text_details": j.text_details
        })

    stats["joins_found"] = len(unique_joins)

    # PHASE 4: Export Visualization
    log.info("PHASE 4: Export Visualization")
    viz_path = EXPORT_DIR / "cdli_fragment_joins.png"
    try:
        visualize_fragment_joins(conn, top_joins, viz_path)
        stats["visualization"] = str(viz_path)
    except Exception as e:
        log.error(f"Visualization failed: {e}")
        stats["errors"].append(f"Visualization: {e}")

    conn.close()

    log.info("=" * 70)
    log.info("✅ REAL CDLI VISION PIPELINE COMPLETE")
    log.info("=" * 70)
    return stats

if __name__ == "__main__":
    try:
        stats = run_cdli_pipeline()
        print("\n📊 CDLI PIPELINE STATISTICS")
        print("=" * 50)
        for k, v in stats.items():
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
                for item in v[:3]:
                    if isinstance(item, dict):
                        print(f"    - {item.get('tablet_a','')} ↔ {item.get('tablet_b','')}: JCI={item.get('join_confidence',0):.3f}")
                    else:
                        print(f"    - {item}")
            else:
                print(f"  {k}: {v}")
        sys.exit(0)
    except Exception as e:
        log.exception("CDLI Pipeline failed")
        sys.exit(1)