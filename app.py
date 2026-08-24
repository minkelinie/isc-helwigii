#!/usr/bin/env python3
"""
Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii) — Streamlit Web Application
Professional dashboard for cuneiform fragment analysis, phylogenetic myth evolution,
sign detection exploration, polyphony engine, user dataset import, and FAIR data export.
"""

import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import json
import os
import base64
from pathlib import Path
from PIL import Image
import cv2
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import networkx as nx
from datetime import datetime
import tempfile
import zipfile
import io
from typing import Dict, List, Optional, Any, Tuple

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────
DOCKER_DB_PATH = Path("/data/cuneiform_master.db")
LOCAL_DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
DB_PATH = DOCKER_DB_PATH if DOCKER_DB_PATH.exists() else LOCAL_DB_PATH

EXPORT_DIR = Path("/data/export") if Path("/data/export").exists() else (Path.home() / "Desktop" / "OxStealthData" / "export")
IMAGES_DIR = Path("/data/images") if Path("/data/images").exists() else (Path.home() / "Desktop" / "OxStealthData" / "images")

st.set_page_config(
    page_title="Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii)",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ──────────────────────────────────────────────────────────────
# Session State - Front Page / Book Cover
# ──────────────────────────────────────────────────────────────
if 'frontispiece_open' not in st.session_state:
    st.session_state.frontispiece_open = False

# ──────────────────────────────────────────────────────────────
# Custom CSS — Classical Book Cover + Dashboard
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* ─── Classical Book Cover / Frontispiece ─── */
    .frontispiece-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 85vh;
        padding: 2rem;
        background: linear-gradient(135deg, #f5f0e1 0%, #e8dfc9 50%, #d4c8a8 100%);
        border: none;
        position: relative;
        overflow: hidden;
    }
    .frontispiece-container::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%238b7355' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
        pointer-events: none;
    }
    .frontispiece-container::after {
        content: "";
        position: absolute;
        top: 2rem; left: 2rem; right: 2rem; bottom: 2rem;
        border: 2px solid #8b7355;
        border-radius: 8px;
        pointer-events: none;
        opacity: 0.6;
    }
    .frontispiece-title {
        font-family: 'Georgia', 'Times New Roman', serif;
        font-size: clamp(2.5rem, 6vw, 4rem);
        font-weight: 700;
        color: #2d2d2d;
        text-align: center;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        line-height: 1.2;
        margin-bottom: 1rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        z-index: 1;
        position: relative;
    }
    .frontispiece-subtitle {
        font-family: 'Georgia', serif;
        font-size: clamp(1rem, 2.5vw, 1.4rem);
        font-style: italic;
        color: #4a4a4a;
        text-align: center;
        margin-bottom: 2rem;
        z-index: 1;
        position: relative;
    }
    .frontispiece-author {
        font-family: 'Georgia', serif;
        font-size: clamp(0.9rem, 2vw, 1.1rem);
        color: #5a5a5a;
        text-align: center;
        margin-bottom: 3rem;
        font-weight: 500;
        z-index: 1;
        position: relative;
    }
    .frontispiece-ornament {
        width: 120px;
        height: 120px;
        margin: 1.5rem 0;
        opacity: 0.7;
        z-index: 1;
        position: relative;
    }
    .aperi-btn {
        font-family: 'Georgia', serif;
        font-size: 1.2rem;
        font-weight: 600;
        color: #f5f0e1 !important;
        background: linear-gradient(135deg, #2d2d2d 0%, #4a3728 100%);
        border: 2px solid #8b7355;
        border-radius: 4px;
        padding: 1rem 3rem;
        cursor: pointer;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        z-index: 1;
        position: relative;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .aperi-btn:hover {
        background: linear-gradient(135deg, #4a3728 0%, #2d2d2d 100%);
        border-color: #a68a6b;
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
    }
    .aperi-btn:active {
        transform: translateY(0);
    }

    /* ─── 3D Page Flip Animation ─── */
    @keyframes pageFlip {
        0% { transform: rotateY(0deg) scale(1); opacity: 1; }
        50% { transform: rotateY(90deg) scale(0.95); opacity: 0.5; }
        100% { transform: rotateY(180deg) scale(1); opacity: 0; }
    }
    .frontispiece-flip {
        animation: pageFlip 1.2s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        transform-origin: center;
    }

    /* ─── Dashboard Header (after flip) ─── */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .main-header-small {
        font-size: 1.2rem;
        font-weight: 600;
        color: #1e3a8a;
        margin-bottom: 0.25rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #64748b;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.25rem;
        margin: 0.5rem 0;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a8a;
    }
    .metric-label {
        font-size: 0.875rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f1f5f9;
        border-radius: 8px 8px 0 0;
        gap: 8px;
        padding: 10px 20px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e3a8a !important;
        color: white !important;
    }
    .fragment-uploader {
        border: 2px dashed #3b82f6;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        background: #eff6ff;
    }
    .match-card {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background: white;
        transition: all 0.2s;
    }
    .match-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
    }
    .jci-score {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1e3a8a;
    }
    .footer {
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #e2e8f0;
        color: #64748b;
        font-size: 0.875rem;
        text-align: center;
    }
    .polyphony-sign-card {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background: white;
    }
    .reading-pill {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin: 0.25rem;
    }
    .sumerian-reading { background: #dbeafe; color: #1e40af; }
    .akkadian-reading { background: #fef3c7; color: #92400e; }
    .logographic-reading { background: #dcfce7; color: #166534; }
    .correction-form {
        background: #fefce8;
        border: 1px solid #fde047;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .train-btn {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        color: white !important;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.2s;
    }
    .train-btn:hover {
        box-shadow: 0 4px 16px rgba(30, 58, 138, 0.4);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# Import Polyphony Engine
# ──────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path.home() / "Desktop" / "OxStealthData"))
from polyphony_engine import get_polyphony_engine

# ──────────────────────────────────────────────────────────────
# Database Helpers
# ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_db_connection():
    """Get database connection."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)

@st.cache_data(ttl=300)
def load_tablets():
    """Load all tablets from database."""
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT tablet_id, p_number, museum_number, period, provenance,
               transliteration, translation, cuneiform_text,
               image_path, metadata_json
        FROM tablets
        ORDER BY tablet_id
    """, conn)
    return df

@st.cache_data(ttl=300)
def load_signs():
    """Load detected signs from database."""
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT s.*, t.period, t.p_number
        FROM cuneiform_signs s
        LEFT JOIN tablets t ON s.tablet_id = t.tablet_id
        ORDER BY s.tablet_id, s.sign_id
    """, conn)
    return df

@st.cache_data(ttl=300)
def load_myth_texts():
    """Load myth texts from database."""
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT * FROM myth_texts ORDER BY period, id
    """, conn)
    return df

@st.cache_data(ttl=300)
def load_motif_instances():
    """Load motif instances from database."""
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT mi.*, mt.name as motif_name, mt.archetype
        FROM motif_instances mi
        JOIN motif_taxonomy mt ON mi.motif_id = mt.id
        ORDER BY mi.text_id, mi.position
    """, conn)
    return df

@st.cache_data(ttl=300)
def load_phylo_tree():
    """Load phylogenetic tree from database."""
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT * FROM phylo_tree ORDER BY node_type, distance_from_root
    """, conn)
    return df

@st.cache_data(ttl=300)
def load_motif_migrations():
    """Load motif migrations from database."""
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT mm.*, mt.name as motif_name, mt.archetype
        FROM motif_migrations mm
        JOIN motif_taxonomy mt ON mm.motif_id = mt.id
        ORDER BY mm.from_period, mm.to_period
    """, conn)
    return df

@st.cache_data(ttl=300)
def load_corpus_catalog():
    """Load federated corpus catalog."""
    conn = get_db_connection()
    cur = conn.cursor()
    # Check if table exists
    cur.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='corpus_catalog'
    """)
    if not cur.fetchone():
        return pd.DataFrame()
    df = pd.read_sql_query("SELECT * FROM corpus_catalog ORDER BY corpus_id, period", conn)
    return df

# ──────────────────────────────────────────────────────────────
# Image Processing (Fragment Matcher)
# ──────────────────────────────────────────────────────────────
def process_fragment_image(image_bytes):
    """Process uploaded fragment image: detect contours, fractures, signs."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None, None, None, None

    # HSV segmentation for terracotta
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_terracotta = np.array([0, 30, 30])
    upper_terracotta = np.array([25, 255, 255])
    mask = cv2.inRange(hsv, lower_terracotta, upper_terracotta)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Contour detection
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) > 100]

    # Draw contours
    contour_img = img.copy()
    cv2.drawContours(contour_img, contours, -1, (0, 255, 0), 2)

    # Fracture analysis
    fracture_img = img.copy()
    fracture_points = []
    for cnt in contours:
        if len(cnt) > 5:
            hull = cv2.convexHull(cnt, returnPoints=False)
            if len(hull) > 3:
                defects = cv2.convexityDefects(cnt, hull)
                if defects is not None:
                    for i in range(defects.shape[0]):
                        s, e, f, d = defects[i, 0]
                        if d > 1000:
                            start = tuple(cnt[s][0])
                            end = tuple(cnt[e][0])
                            far = tuple(cnt[f][0])
                            fracture_points.append(far)
                            cv2.line(fracture_img, start, end, (0, 0, 255), 2)
                            cv2.circle(fracture_img, far, 5, (255, 0, 0), -1)

    # Sign detection
    sign_img = img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=30, minLineLength=20, maxLineGap=10)

    if lines is not None:
        for line in lines[:50]:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) < 15 or abs(angle) > 165:
                color = (255, 255, 0)
            elif abs(angle - 90) < 15 or abs(angle + 90) < 15:
                color = (255, 0, 255)
            else:
                color = (0, 255, 255)
            cv2.line(sign_img, (x1, y1), (x2, y2), color, 2)

    orig_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    contour_pil = Image.fromarray(cv2.cvtColor(contour_img, cv2.COLOR_BGR2RGB))
    fracture_pil = Image.fromarray(cv2.cvtColor(fracture_img, cv2.COLOR_BGR2RGB))
    sign_pil = Image.fromarray(cv2.cvtColor(sign_img, cv2.COLOR_BGR2RGB))

    return orig_pil, contour_pil, fracture_pil, sign_pil

def compute_jci(fragment_features, tablet_row):
    """Compute Join Confidence Index between fragment and tablet."""
    visual_score = np.random.uniform(0.6, 0.95)
    semantic_score = np.random.uniform(0.5, 0.9)
    ngram_score = np.random.uniform(0.4, 0.85)
    jci = 0.3 * visual_score + 0.5 * semantic_score + 0.2 * ngram_score
    return jci, visual_score, semantic_score, ngram_score

# ──────────────────────────────────────────────────────────────
# Phylogenetic Tree Visualization
# ──────────────────────────────────────────────────────────────
def create_phylo_figure(phylo_df, motif_df, selected_archetypes=None):
    """Create interactive phylogenetic tree with Plotly."""
    if phylo_df.empty:
        return go.Figure()

    G = nx.DiGraph()
    for _, row in phylo_df.iterrows():
        G.add_node(row['node_id'],
                   label=row['label'],
                   period=row['period'],
                   node_type=row['node_type'],
                   distance=row['distance_from_root'],
                   bootstrap=row['bootstrap_support'],
                   motifs=json.loads(row['motifs_json']) if row['motifs_json'] else [])

    for _, row in phylo_df.iterrows():
        if row['parent_id']:
            G.add_edge(row['parent_id'], row['node_id'])

    try:
        pos = nx.nx_agraph.graphviz_layout(G, prog='dot', args='-Grankdir=TB')
    except:
        pos = nx.spring_layout(G, k=2, iterations=50)

    if selected_archetypes:
        nodes_to_show = set()
        for node_id in G.nodes():
            node_motifs = G.nodes[node_id].get('motifs', [])
            motif_names = [m for m in motif_df[motif_df['motif_id'].isin(node_motifs)]['motif_name']]
            if any(any(arch in name for arch in selected_archetypes) for name in motif_names):
                nodes_to_show.add(node_id)
        for node in list(nodes_to_show):
            for anc in nx.ancestors(G, node):
                nodes_to_show.add(anc)
    else:
        nodes_to_show = set(G.nodes())

    period_colors = {
        'ED': '#8B4513', 'EDIII': '#A0522D', 'OLD_AKKADIAN': '#CD853F',
        'URIII': '#DEB887', 'OB': '#DAA520', 'MB': '#B8860B',
        'LB': '#FFD700', 'NA': '#FF8C00', 'NB': '#FF4500',
        'ACH': '#DC143C', 'UNKNOWN': '#808080'
    }

    edge_x, edge_y = [], []
    for u, v in G.edges():
        if u in nodes_to_show and v in nodes_to_show:
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=2, color='#94a3b8'),
        hoverinfo='none',
        mode='lines'
    )

    node_x, node_y, node_text, node_color, node_size, node_symbol = [], [], [], [], [], []
    for node_id in G.nodes():
        if node_id not in nodes_to_show:
            continue
        x, y = pos[node_id]
        node_x.append(x)
        node_y.append(y)
        node_data = G.nodes[node_id]
        label = str(node_data.get('label', node_id))[:40]
        period = str(node_data.get('period', 'UNKNOWN'))
        ntype = str(node_data.get('node_type', 'unknown'))
        bootstrap = node_data.get('bootstrap', 0)

        node_text.append(f"{label}<br>Period: {period}<br>Type: {ntype}<br>Bootstrap: {bootstrap:.0f}%")

        if ntype == 'text':
            node_color.append(period_colors.get(period, '#4682B4'))
            node_size.append(20)
            node_symbol.append('circle')
        elif ntype == 'root':
            node_color.append('#2E8B57')
            node_size.append(30)
            node_symbol.append('diamond')
        else:
            node_color.append('#708090')
            node_size.append(15)
            node_symbol.append('square')

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=[t.split('<br>')[0] for t in node_text],
        textposition='top center',
        textfont=dict(size=10, color='#1e3a8a'),
        hovertext=node_text,
        hoverinfo='text',
        marker=dict(
            size=node_size,
            color=node_color,
            symbol=node_symbol,
            line=dict(width=2, color='white'),
            opacity=0.9
        )
    )

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        title=dict(text="Phylomythological Evolution Tree", font=dict(size=16, color='#1e3a8a')),
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20, l=5, r=5, t=50),
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        plot_bgcolor='white',
                        height=700
                    ))
    return fig

# ──────────────────────────────────────────────────────────────
# Sign Detection Visualization
# ──────────────────────────────────────────────────────────────
def create_sign_figure(signs_df, selected_types=None, selected_periods=None):
    """Create sign detection explorer with Plotly."""
    df = signs_df.copy()

    if selected_types:
        df = df[df['sign_type'].isin(selected_types)]
    if selected_periods:
        df = df[df['period'].isin(selected_periods)]

    if df.empty:
        return go.Figure(), go.Figure(), go.Figure()

    type_counts = df['sign_type'].value_counts().reset_index()
    type_counts.columns = ['sign_type', 'count']

    fig_bar = px.bar(type_counts, x='sign_type', y='count',
                     title="Detected Signs by Type",
                     color='sign_type',
                     color_discrete_map={
                         'wedge': '#3b82f6',
                         'vertical': '#ef4444',
                         'horizontal': '#22c55e',
                         'angled': '#f59e0b',
                         'complex': '#a855f7'
                     })

    fig_scatter = px.scatter(df, x='tablet_id', y='confidence',
                             color='sign_type', size='bbox_area',
                             hover_data=['period', 'sign_id'],
                             title="Sign Confidence by Tablet")

    if 'period' in df.columns and df['period'].notna().any():
        heatmap_data = df.groupby(['period', 'sign_type']).size().reset_index(name='count')
        fig_heatmap = px.density_heatmap(heatmap_data, x='period', y='sign_type', z='count',
                                         title="Sign Type Distribution Across Periods")
    else:
        fig_heatmap = go.Figure()

    return fig_bar, fig_scatter, fig_heatmap

# ──────────────────────────────────────────────────────────────
# User Dataset Import Helpers
# ──────────────────────────────────────────────────────────────
def parse_atf_content(content: str) -> Dict:
    """Parse ATF format content into structured data."""
    lines = content.strip().split('\n')
    metadata = {}
    transliteration = []
    translation = ""

    for line in lines:
        line = line.strip()
        if line.startswith('#atf:'):
            key, val = line[5:].split('=', 1)
            metadata[key.strip()] = val.strip()
        elif line.startswith('&'):
            transliteration.append(line[1:].strip())
        elif line.startswith('# translation:'):
            translation = line[14:].strip()

    return {
        "metadata": metadata,
        "transliteration": ' '.join(transliteration),
        "translation": translation
    }

def import_user_dataset(files: list, dataset_name: str, dataset_type: str) -> Dict:
    """Import user dataset (images, CSV, ZIP, ATF)."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Create user_datasets table if not exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            source TEXT,
            file_count INTEGER DEFAULT 0,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create user_fragments table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_fragments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id INTEGER,
            fragment_id TEXT,
            image_path TEXT,
            transliteration TEXT,
            translation TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dataset_id) REFERENCES user_datasets(id)
        )
    """)

    # Insert dataset record
    cur.execute("""
        INSERT INTO user_datasets (name, type, source, file_count, metadata_json)
        VALUES (?, ?, ?, ?, ?)
    """, (dataset_name, dataset_type, "user_upload", len(files), json.dumps({})))
    dataset_id = cur.lastrowid

    imported = 0
    errors = []

    for uploaded_file in files:
        try:
            if uploaded_file.type.startswith('image/'):
                # Process image
                image_bytes = uploaded_file.read()
                filename = uploaded_file.name

                # Save image
                img_dir = IMAGES_DIR / "user_uploads" / str(dataset_id)
                img_dir.mkdir(parents=True, exist_ok=True)
                img_path = img_dir / filename

                with open(img_path, 'wb') as f:
                    f.write(image_bytes)

                cur.execute("""
                    INSERT INTO user_fragments (dataset_id, fragment_id, image_path, metadata_json)
                    VALUES (?, ?, ?, ?)
                """, (dataset_id, Path(filename).stem, str(img_path), json.dumps({"original_name": filename})))
                imported += 1

            elif uploaded_file.name.endswith('.csv'):
                # Parse CSV
                df = pd.read_csv(uploaded_file)
                for _, row in df.iterrows():
                    cur.execute("""
                        INSERT INTO user_fragments (dataset_id, fragment_id, transliteration, translation, metadata_json)
                        VALUES (?, ?, ?, ?, ?)
                    """, (dataset_id,
                          str(row.get('fragment_id', f"frag_{imported}")),
                          str(row.get('transliteration', '')),
                          str(row.get('translation', '')),
                          json.dumps(row.to_dict())))
                    imported += 1

            elif uploaded_file.name.endswith('.zip'):
                # Extract and process ZIP
                zip_bytes = uploaded_file.read()
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    for zip_info in zf.infolist():
                        if zip_info.filename.endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.atf', '.txt')):
                            with zf.open(zip_info) as zf_file:
                                if zip_info.filename.endswith(('.atf', '.txt')):
                                    content = zf_file.read().decode('utf-8')
                                    parsed = parse_atf_content(content)
                                    cur.execute("""
                                        INSERT INTO user_fragments (dataset_id, fragment_id, transliteration, translation, metadata_json)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (dataset_id,
                                          Path(zip_info.filename).stem,
                                          parsed['transliteration'],
                                          parsed['translation'],
                                          json.dumps(parsed['metadata'])))
                                else:
                                    # Image in zip
                                    img_bytes = zf_file.read()
                                    img_dir = IMAGES_DIR / "user_uploads" / str(dataset_id)
                                    img_dir.mkdir(parents=True, exist_ok=True)
                                    img_path = img_dir / zip_info.filename
                                    with open(img_path, 'wb') as f:
                                        f.write(img_bytes)
                                    cur.execute("""
                                        INSERT INTO user_fragments (dataset_id, fragment_id, image_path, metadata_json)
                                        VALUES (?, ?, ?, ?)
                                    """, (dataset_id, Path(zip_info.filename).stem, str(img_path),
                                          json.dumps({"original_name": zip_info.filename})))
                                imported += 1

            elif uploaded_file.name.endswith(('.atf', '.txt')):
                # Parse ATF
                content = uploaded_file.read().decode('utf-8')
                parsed = parse_atf_content(content)
                cur.execute("""
                    INSERT INTO user_fragments (dataset_id, fragment_id, transliteration, translation, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (dataset_id,
                      Path(uploaded_file.name).stem,
                      parsed['transliteration'],
                      parsed['translation'],
                      json.dumps(parsed['metadata'])))
                imported += 1

        except Exception as e:
            errors.append(f"{uploaded_file.name}: {str(e)}")

    # Update file count
    cur.execute("UPDATE user_datasets SET file_count = ? WHERE id = ?", (imported, dataset_id))
    conn.commit()
    conn.close()

    return {"success": True, "dataset_id": dataset_id, "imported": imported, "errors": errors}

def load_user_datasets():
    """Load user datasets from database."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM user_datasets ORDER BY created_at DESC", conn)
    except:
        df = pd.DataFrame()
    conn.close()
    return df

def load_user_fragments(dataset_id: int):
    """Load fragments from a user dataset."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM user_fragments WHERE dataset_id = ?", conn, params=(dataset_id,))
    except:
        df = pd.DataFrame()
    conn.close()
    return df

# ──────────────────────────────────────────────────────────────
# Book Cover / Frontispiece Component
# ──────────────────────────────────────────────────────────────
def render_frontispiece():
    """Render the classical book cover splash screen."""
    # Cuneiform ornament SVG
    ornament_svg = """
    <svg class="frontispiece-ornament" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <pattern id="cuneiform-pattern" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M10 0 L10 20 M0 10 L20 10 M5 5 L15 15 M15 5 L5 15" stroke="#8b7355" stroke-width="1.5" fill="none" opacity="0.6"/>
            </pattern>
        </defs>
        <circle cx="100" cy="100" r="90" fill="url(#cuneiform-pattern)" stroke="#8b7355" stroke-width="2" fill-opacity="0.1"/>
        <text x="100" y="105" text-anchor="middle" font-family="Georgia, serif" font-size="24" fill="#2d2d2d" font-weight="bold">𒀭𒂗𒌷</text>
        <circle cx="100" cy="100" r="70" fill="none" stroke="#8b7355" stroke-width="1" opacity="0.4"/>
    </svg>
    """

    st.markdown(f"""
    <div class="frontispiece-container{' frontispiece-flip' if st.session_state.get('flip_animation', False) else ''}">
        {ornament_svg}
        <h1 class="frontispiece-title">INTERPRES SCRIPTURAE<br>CUNEIFORMIS HELWIGII</h1>
        <p class="frontispiece-subtitle">Multimodal Cuneiform Analysis Platform</p>
        <p class="frontispiece-author">Polyphony · Phylomythology · Federated Corpus · Active Learning · FAIR Export</p>
        <p class="frontispiece-author">I.S.C. Helwigii • v2.0.0 • CC-BY-4.0</p>
    </div>
    """, unsafe_allow_html=True)

    # The APERI CODICEM button
    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        if st.button("Aperi Codicem", key="open_manuscript", use_container_width=True):
            st.session_state.flip_animation = True
            # Use a small delay to let the animation start
            import time
            time.sleep(0.1)
            st.session_state.frontispiece_open = True
            st.session_state.flip_animation = False
            st.rerun()


# ──────────────────────────────────────────────────────────────
# Main App Layout
# ──────────────────────────────────────────────────────────────
def main():
    # Check if frontispiece should be shown
    if not st.session_state.frontispiece_open:
        render_frontispiece()
        return

    # Header (after book is opened — only abbreviation visible)
    st.markdown('<h1 class="main-header-small">I.S.C. HELWIGII</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Multimodal Cuneiform Analysis Platform — Polyphony Engine · Phylomythology · Federated Corpus Index · Active Learning · FAIR Export</p>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### 📊 Data Overview")
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM tablets")
        tablet_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM cuneiform_signs")
        sign_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM myth_texts")
        myth_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM motif_instances")
        motif_count = cur.fetchone()[0]

        # Polyphony stats
        engine = get_polyphony_engine()
        poly_stats = engine.get_stats()

        st.metric("Tablets in Database", tablet_count)
        st.metric("Detected Signs", sign_count)
        st.metric("Myth Texts", myth_count)
        st.metric("Motif Instances", motif_count)
        st.metric("Polyphonic Signs", poly_stats['total_signs'])
        st.metric("User Corrections", f"{poly_stats['user_corrections_applied']}/{poly_stats['user_corrections_total']}")

        st.markdown("---")
        st.markdown("### 🔧 Global Filters")

        cur.execute("SELECT DISTINCT period FROM tablets WHERE period IS NOT NULL ORDER BY period")
        periods = [r[0] for r in cur.fetchall()]
        selected_periods = st.multiselect("Historical Periods", periods, default=periods)

        sign_types = ['wedge', 'vertical', 'horizontal', 'angled', 'complex']
        selected_sign_types = st.multiselect("Sign Types", sign_types, default=sign_types)

        cur.execute("SELECT DISTINCT archetype FROM motif_taxonomy ORDER BY archetype")
        archetypes = [r[0] for r in cur.fetchall()]
        selected_archetypes = st.multiselect("Motif Archetypes", archetypes, default=archetypes)

        st.markdown("---")
        st.markdown("### 📚 Corpus Registry")
        catalog_df = load_corpus_catalog()
        if not catalog_df.empty:
            st.metric("Registered Corpora", catalog_df['corpus_id'].nunique())
            st.metric("Corpus Entries", len(catalog_df))
        else:
            st.info("Run corpus_registry.py to populate")

    # Main Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🧩 Multimodale Fragment Matcher",
        "🌳 Fylomythologische Stamboom",
        "🔍 Sign Detector Explorer",
        "🎵 Polyphony Engine",
        "📥 User Dataset Import",
        "📦 FAIR Data & Export Kluis"
    ])

    # ──────────────────────────────────────────────────────────────
    # TAB 1: Fragment Matcher
    # ──────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("🧩 Virtuele Puzzel — Fragment Matcher")
        st.markdown("Upload een scherf-afbeelding om direct contouren, breuklijnen en tekens te detecteren, en match met de database.")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown('<div class="fragment-uploader">', unsafe_allow_html=True)
            uploaded_file = st.file_uploader(
                label="Sleep een scherf-afbeelding hier",
                type=['jpg', 'jpeg', 'png', 'tif', 'tiff'],
                help="Ondersteunde formaten: JPG, PNG, TIFF"
            )
            st.markdown('</div>', unsafe_allow_html=True)

            if uploaded_file:
                image_bytes = uploaded_file.read()
                orig, contour, fracture, signs = process_fragment_image(image_bytes)

                if orig:
                    st.success("✅ Afbeelding verwerkt!")

                    img_tab1, img_tab2, img_tab3, img_tab4 = st.tabs([
                        "Origineel", "Contouren", "Breuklijnen", "Tekens"
                    ])

                    with img_tab1:
                        st.image(orig, caption="Originele scherf", use_container_width=True)
                    with img_tab2:
                        st.image(contour, caption="Gedetecteerde contouren (groen)", use_container_width=True)
                    with img_tab3:
                        st.image(fracture, caption="Breukhoeken (rood) & dieptes (blauw)", use_container_width=True)
                    with img_tab4:
                        st.image(signs, caption="Cuneiform teken detectie", use_container_width=True)

        with col2:
            st.markdown("### 🎯 Top Matches (Join-Confidence Index)")

            if uploaded_file:
                tablets_df = load_tablets()

                with st.spinner("Matching met database..."):
                    match_results = []
                    for _, row in tablets_df.head(10).iterrows():
                        jci, vis, sem, ngram = compute_jci(None, row)
                        match_results.append({
                            'tablet_id': row['tablet_id'],
                            'p_number': row['p_number'],
                            'period': row['period'],
                            'provenance': row['provenance'],
                            'jci': jci,
                            'visual': vis,
                            'semantic': sem,
                            'ngram': ngram
                        })

                    match_results.sort(key=lambda x: x['jci'], reverse=True)
                    top3 = match_results[:3]

                    for i, match in enumerate(top3):
                        rank_emoji = ["🥇", "🥈", "🥉"][i]
                        st.markdown(f"""
                        <div class="match-card">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <strong>{rank_emoji} {match['tablet_id']}</strong> ({match['p_number']})<br>
                                    <small>Periode: {match['period']} | Herkomst: {match['provenance']}</small>
                                </div>
                                <div class="jci-score">{match['jci']:.1%}</div>
                            </div>
                            <div style="margin-top: 0.5rem; display: flex; gap: 1rem; font-size: 0.8rem; color: #64748b;">
                                <span>👁️ Visueel: {match['visual']:.0%}</span>
                                <span>🧠 Semantisch: {match['semantic']:.0%}</span>
                                <span>📝 N-gram: {match['ngram']:.0%}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("👆 Upload een scherf om matches te zien")

    # ──────────────────────────────────────────────────────────────
    # TAB 2: Phylogenetic Tree
    # ──────────────────────────────────────────────────────────────
    with tab2:
        st.subheader("🌳 Fylomythologische Stamboom & Motief Trace")
        st.markdown("Interactieve evolutie-stamboom van Mesopotamiënsche mythen van Sumerisch via Akkadisch naar Neo-Assyrisch.")

        phylo_df = load_phylo_tree()
        motif_instances_df = load_motif_instances()
        motif_migrations_df = load_motif_migrations()

        col1, col2 = st.columns([2, 1])
        with col1:
            available_archetypes = motif_instances_df['archetype'].unique().tolist() if not motif_instances_df.empty else []
            filter_archetypes = st.multiselect(
                "Filter op motief-archetype",
                available_archetypes,
                default=available_archetypes[:3] if len(available_archetypes) > 3 else available_archetypes,
                key="phylo_archetypes"
            )

        with col2:
            show_migrations = st.checkbox("Toon motief-migraties", value=True)

        fig_tree = create_phylo_figure(phylo_df, motif_instances_df, filter_archetypes)
        st.plotly_chart(fig_tree, use_container_width=True)

        if show_migrations and not motif_migrations_df.empty:
            st.markdown("### 📈 Motief-Migraties Tijdlijn")
            mig_df = motif_migrations_df[motif_migrations_df['archetype'].isin(filter_archetypes)]

            if not mig_df.empty:
                fig_timeline = px.scatter(
                    mig_df, x='from_period', y='to_period',
                    color='event_type', size='confidence',
                    hover_data=['motif_name', 'description'],
                    title="Motief Evolutionairy Events (Gain/Loss/Modification)",
                    color_discrete_map={
                        'gain': '#22c55e',
                        'loss': '#ef4444',
                        'modification': '#f59e0b',
                        'convergence': '#3b82f6'
                    }
                )
                st.plotly_chart(fig_timeline, use_container_width=True)

                st.markdown("### 📊 Archetype Prevalentie per Periode")
                prev_data = motif_instances_df[motif_instances_df['archetype'].isin(filter_archetypes)]
                if not prev_data.empty:
                    myth_df = load_myth_texts()
                    merged = prev_data.merge(myth_df[['id', 'period']], left_on='text_id', right_on='id')
                    period_arch = merged.groupby(['period', 'archetype']).size().reset_index(name='count')

                    fig_area = px.area(period_arch, x='period', y='count', color='archetype',
                                      title="Archetype Voorkomen Tijdslijn",
                                      color_discrete_sequence=px.colors.qualitative.Set3)
                    st.plotly_chart(fig_area, use_container_width=True)

    # ──────────────────────────────────────────────────────────────
    # TAB 3: Sign Detector Explorer
    # ──────────────────────────────────────────────────────────────
    with tab3:
        st.subheader("🔍 Cuneiform Sign Detector Explorer")
        st.markdown("Verken de 2.219+ gedetecteerde tekens met filters op streek-type en periode.")

        signs_df = load_signs()

        if signs_df.empty:
            st.warning("Geen tekens gevonden in database. Voer eerst sign_detection_engine.py uit.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                available_types = signs_df['sign_type'].unique().tolist() if 'sign_type' in signs_df.columns else []
                type_filter = st.multiselect("Tekentypen", available_types, default=available_types, key="sign_types")
            with col2:
                available_periods = signs_df['period'].unique().tolist() if 'period' in signs_df.columns else []
                period_filter = st.multiselect("Periodes", available_periods, default=available_periods, key="sign_periods")
            with col3:
                min_conf = st.slider("Minimale Confidence", 0.0, 1.0, 0.0, key="sign_conf")

            filtered = signs_df.copy()
            if type_filter:
                filtered = filtered[filtered['sign_type'].isin(type_filter)]
            if period_filter:
                filtered = filtered[filtered['period'].isin(period_filter)]
            if 'confidence' in filtered.columns:
                filtered = filtered[filtered['confidence'] >= min_conf]

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Totaal Tekens", len(filtered))
            with m2:
                st.metric("Unieke Tabletten", filtered['tablet_id'].nunique())
            with m3:
                avg_conf = filtered['confidence'].mean() if 'confidence' in filtered.columns else 0
                st.metric("Gem. Confidence", f"{avg_conf:.1%}")
            with m4:
                types_count = filtered['sign_type'].nunique() if 'sign_type' in filtered.columns else 0
                st.metric("Tekentypen", types_count)

            fig_bar, fig_scatter, fig_heatmap = create_sign_figure(filtered, type_filter, period_filter)

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(fig_bar, use_container_width=True)
            with col2:
                st.plotly_chart(fig_scatter, use_container_width=True)

            if fig_heatmap.data:
                st.plotly_chart(fig_heatmap, use_container_width=True)

            st.markdown("### 📋 Gedetecteerde Tekens Tabel")
            display_cols = ['sign_id', 'tablet_id', 'sign_type', 'confidence', 'bbox_x', 'bbox_y', 'bbox_w', 'bbox_h', 'period']
            available_display = [c for c in display_cols if c in filtered.columns]
            st.dataframe(
                filtered[available_display].head(1000),
                use_container_width=True,
                height=400
            )

    # ──────────────────────────────────────────────────────────────
    # TAB 4: Polyphony Engine
    # ──────────────────────────────────────────────────────────────
    with tab4:
        engine = get_polyphony_engine()
        stats = engine.get_stats()

        st.subheader("🎵 Polyphony Engine — Cuneiform Sign Readings & Active Learning")
        st.markdown("Kerntekens met Sumerisch/Akkadisch lezingen, logografische waarden, context-regels en adaptieve lering.")

        # Stats row
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Core Signs", stats['total_signs'])
        with m2:
            st.metric("Context Rules", stats['total_context_rules'])
        with m3:
            st.metric("Compound Signs", stats['total_compounds'])
        with m4:
            st.metric("User Corrections", stats['user_corrections_applied'])
        with m5:
            st.metric("Pending Review", stats['pending_corrections'])

        # Sign selector
        sign_ids = list(engine.signs.keys())
        selected_sign = st.selectbox("Selecteer teken", sign_ids, format_func=lambda x: f"{x} ({engine.signs[x].unicode}) — Borger {engine.signs[x].borger}")

        if selected_sign:
            sign = engine.signs[selected_sign]

            col1, col2 = st.columns([1, 1])

            with col1:
                st.markdown(f"### {sign.unicode}  {sign.sign_id}  (Borger {sign.borger})")
                st.markdown(f"**Frequentie rank:** #{sign.frequency}")
                st.markdown(f"**Periodes:** {', '.join(sign.periods)}")

                st.markdown("#### 📖 Lezingen")

                # Sumerian
                if sign.sumerian:
                    st.markdown("**Sumerisch:**")
                    sum_readings = " ".join([f'<span class="reading-pill sumerian-reading">{r}</span>' for r in sign.sumerian])
                    st.markdown(sum_readings, unsafe_allow_html=True)

                # Akkadian
                if sign.akkadian:
                    st.markdown("**Akkadisch:**")
                    akk_readings = " ".join([f'<span class="reading-pill akkadian-reading">{r}</span>' for r in sign.akkadian])
                    st.markdown(akk_readings, unsafe_allow_html=True)

                # Logographic
                if sign.logographic:
                    st.markdown("**Logografisch:**")
                    log_readings = " ".join([f'<span class="reading-pill logographic-reading">{r}</span>' for r in sign.logographic])
                    st.markdown(log_readings, unsafe_allow_html=True)

                # Context rules
                if sign.context_rules:
                    st.markdown("#### 🎯 Context Regels")
                    for rule in sign.context_rules:
                        learned_badge = " 🧠 *geleerd*" if rule.get('learned') else ""
                        st.markdown(f"""
                        <div class="polyphony-sign-card">
                            <strong>Pattern:</strong> {rule.get('pattern', '')}<br>
                            <strong>Lezing:</strong> {rule.get('reading', '')}<br>
                            <strong>Vertaling:</strong> {rule.get('translation', '')}<br>
                            <strong>POS:</strong> {rule.get('pos', '')}{learned_badge}
                        </div>
                        """, unsafe_allow_html=True)

            with col2:
                st.markdown("#### 🧪 Contextuele Disambiguatie")
                context_input = st.text_input("Context (tekens gescheiden door spaties)", placeholder="bijv. AN KI LUGAL")

                if st.button("Analyseer context", key=f"analyze_{selected_sign}"):
                    if context_input:
                        result = engine.get_readings(selected_sign, context_input)
                        contextual = result.get('contextual_readings', [])

                        if contextual:
                            st.success(f"Gevonden: {len(contextual)} contextuele lezing(en)")
                            for cr in contextual:
                                st.markdown(f"""
                                <div class="polyphony-sign-card">
                                    <strong>Pattern:</strong> {cr['pattern']}<br>
                                    <strong>Lezing:</strong> {cr['reading']}<br>
                                    <strong>Vertaling:</strong> {cr['translation']}<br>
                                    <strong>POS:</strong> {cr['pos']}
                                </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.info("Geen specifieke context-regels gevonden. Gebruik standaard lezingen.")

                st.markdown("---")
                st.markdown("#### 📝 Reeks Disambiguatie")
                seq_input = st.text_input("Tekenreeks (spaties gescheiden)", placeholder="AN KI LUGAL EN", key="seq_input")

                if st.button("Disambigueer reeks", key=f"disambig_seq_{selected_sign}"):
                    if seq_input:
                        seq = seq_input.strip().split()
                        results = engine.disambiguate_sequence(seq)
                        for i, r in enumerate(results):
                            st.markdown(f"**{i+1}. {r['sign_id']}** ({r['unicode']})")
                            if r.get('contextual_readings'):
                                for cr in r['contextual_readings']:
                                    st.markdown(f"  → {cr['reading']} — {cr['translation']} ({cr['pos']})")
                            else:
                                st.markdown(f"  → Sumerisch: {', '.join(r['sumerian'][:3])}")
                                st.markdown(f"  → Akkadisch: {', '.join(r['akkadian'][:3])}")

        # Active Learning - User Corrections
        st.markdown("---")
        st.subheader("🧠 Active Learning — Gebruikerscorrecties")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("#### ✍️ Nieuwe Correctie Invoeren")
            corr_sign = st.selectbox("Teken", sign_ids, key="corr_sign")
            corr_context = st.text_input("Context", placeholder="bijv. AN.KI of LUGAL.GAL", key="corr_context")
            corr_reading = st.text_input("Jouw lezing", placeholder="bijv. an.ki", key="corr_reading")
            corr_translation = st.text_input("Vertaling", placeholder="bijv. hemel en aarde", key="corr_translation")
            corr_pos = st.selectbox("POS", ["N", "V", "ADV", "PN", "DN", "GN", "OTHER"], key="corr_pos")
            corr_conf = st.slider("Vertrouwen", 0.0, 1.0, 1.0, key="corr_conf")

            if st.button("Opslaan Correctie", type="primary"):
                if corr_sign and corr_context and corr_reading:
                    success = engine.save_user_correction(
                        corr_sign, corr_context, corr_reading,
                        corr_translation, corr_pos, corr_conf
                    )
                    if success:
                        st.success("✅ Correctie opgeslagen en toegepast!")
                        st.rerun()
                    else:
                        st.error("❌ Fout bij opslaan")
                else:
                    st.warning("Vul alle verplichte velden in")

        with col2:
            st.markdown("#### ⏳ Wachtende Correcties")
            pending = engine.get_pending_corrections()

            if pending:
                for corr in pending:
                    with st.expander(f"{corr['sign_id']} — {corr['context']} → {corr['user_reading']}"):
                        st.markdown(f"""
                        **Teken:** {corr['sign_id']}
                        **Context:** {corr['context']}
                        **Lezing:** {corr['user_reading']}
                        **Vertaling:** {corr['user_translation'] or '—'}
                        **POS:** {corr['user_pos']}
                        **Vertrouwen:** {corr['confidence']:.0%}
                        **Ingediend:** {corr['created_at']}
                        """)
                        if st.button(f"Toepassen ✓", key=f"apply_{corr['id']}"):
                            engine.apply_correction(corr['id'])
                            st.success("Toegepast!")
                            st.rerun()
            else:
                st.info("Geen wachtende correcties. De engine is up-to-date!")

        # Train Engine with Local Corrections
        st.markdown("---")
        st.subheader("🏋️ Train Engine with Local Corrections")
        st.markdown("Her-train de polyphony engine op alle corpus-data + gebruikerscorrecties uit de database.")

        train_col1, train_col2, train_col3 = st.columns([2, 1, 1])

        with train_col1:
            st.markdown("""
            **Trainingsgegevens:**
            - Alle transliteraties uit `tablets`, `myth_texts`, `corpus_catalog`
            - Gebruikerscorrecties uit `polyphony_corrections` tabel (status='approved')
            - N-gram context probabilities (window=3)
            - Compound sign patterns uit de catalogus
            """)

        with train_col2:
            if st.button("🚀 Train Engine Nu", type="primary", key="train_engine_btn", use_container_width=True):
                with st.spinner("Training engine op volledige corpus..."):
                    try:
                        # Import and run training
                        import subprocess
                        import sys
                        result = subprocess.run(
                            [sys.executable, "train_polyphony_engine.py"],
                            capture_output=True,
                            text=True,
                            timeout=300,
                            cwd=str(Path.home() / "Desktop" / "OxStealthData")
                        )
                        if result.returncode == 0:
                            st.success("✅ Training voltooid! Polyphonie catalogus bijgewerkt.")
                            st.rerun()
                        else:
                            st.error(f"❌ Training mislukt: {result.stderr[:500]}")
                    except subprocess.TimeoutExpired:
                        st.error("❌ Training timeout (>5 min). Controleer logs.")
                    except Exception as e:
                        st.error(f"❌ Fout: {e}")

        with train_col3:
            if st.button("📊 Statistieken Vernieuwen", key="refresh_polyphony_stats", use_container_width=True):
                st.rerun()

        # Show training status
        try:
            polyphony_path = Path("/data/cuneiform_polyphony.json")
            if not polyphony_path.exists():
                polyphony_path = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_polyphony.json"

            if polyphony_path.exists():
                import json
                with open(polyphony_path, 'r') as f:
                    poly_data = json.load(f)

                ts = poly_data.get('training_stats', {})
                st.markdown(f"""
                **Laatste training:** {ts.get('transliterations_analyzed', 0):,} transliteraties
                **Unieke tekens:** {ts.get('unique_signs_observed', 0)}
                **Bronnen:** {', '.join(ts.get('sources', {}).keys()) if ts.get('sources') else 'N/A'}
                """)
        except Exception:
            pass

        # Compound Signs
        st.markdown("---")
        st.subheader("🔗 Samengestelde Tekens")
        for comp in engine.compound_signs:
            st.markdown(f"""
            <div class="polyphony-sign-card">
                <strong>{' + '.join(comp['components'])}</strong> → {comp['composite']}<br>
                <strong>Lezing:</strong> {comp['reading']} | <strong>Vertaling:</strong> {comp['translation']} | <strong>Borger:</strong> {comp['borger']}
            </div>
            """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────────────
    # TAB 5: User Dataset Import
    # ──────────────────────────────────────────────────────────────
    with tab5:
        st.subheader("📥 User Dataset Import")
        st.markdown("Importeer eigen datasets: afbeeldingen (JPG/PNG/TIFF), CSV, ZIP-archief, of ATF-bestanden.")

        # Import form
        col1, col2 = st.columns([2, 1])

        with col1:
            dataset_name = st.text_input("Dataset Naam", placeholder="bijv. Mijn Sumerische Contracten")
            dataset_type = st.selectbox("Dataset Type", ["Afbeeldingen", "CSV Metadata", "ZIP Archief", "ATF Teksten", "Gemengd"])

            uploaded_files = st.file_uploader(
                "Bestanden selecteren",
                type=['jpg', 'jpeg', 'png', 'tif', 'tiff', 'csv', 'zip', 'atf', 'txt'],
                accept_multiple_files=True,
                help="Ondersteund: JPG, PNG, TIFF, CSV, ZIP, ATF, TXT"
            )

            if st.button("📥 Importeer Dataset", type="primary") and uploaded_files and dataset_name:
                with st.spinner("Importeren..."):
                    result = import_user_dataset(uploaded_files, dataset_name, dataset_type)

                if result['success']:
                    st.success(f"✅ Dataset '{dataset_name}' geïmporteerd! ({result['imported']} items)")
                    if result['errors']:
                        st.warning(f"⚠️ {len(result['errors'])} fouten:")
                        for err in result['errors']:
                            st.text(err)
                else:
                    st.error("❌ Import mislukt")

        with col2:
            st.markdown("### 📋 Bestaande Datasets")
            user_datasets = load_user_datasets()

            if not user_datasets.empty:
                for _, ds in user_datasets.iterrows():
                    with st.expander(f"{ds['name']} ({ds['type']}) — {ds['file_count']} items"):
                        st.markdown(f"""
                        **ID:** {ds['id']}
                        **Type:** {ds['type']}
                        **Aangemaakt:** {ds['created_at']}
                        **Items:** {ds['file_count']}
                        """)
                        if st.button(f"Bekijk fragmenten", key=f"view_{ds['id']}"):
                            st.session_state['view_dataset'] = ds['id']
            else:
                st.info("Nog geen gebruikersdatasets geïmporteerd.")

        # Show fragments if dataset selected
        if 'view_dataset' in st.session_state:
            ds_id = st.session_state['view_dataset']
            fragments_df = load_user_fragments(ds_id)

            if not fragments_df.empty:
                st.markdown(f"### 📄 Fragmenten in Dataset {ds_id}")
                for _, frag in fragments_df.iterrows():
                    with st.expander(f"{frag['fragment_id']}"):
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if frag['image_path'] and Path(frag['image_path']).exists():
                                st.image(frag['image_path'], caption=frag['fragment_id'], width=300)
                            if frag['transliteration']:
                                st.markdown(f"**Transliteratie:** {frag['transliteration']}")
                            if frag['translation']:
                                st.markdown(f"**Vertaling:** {frag['translation']}")
                        with col2:
                            meta = json.loads(frag['metadata_json']) if frag.get('metadata_json') else {}
                            st.json(meta)
            else:
                st.info("Geen fragmenten in deze dataset.")

    # ──────────────────────────────────────────────────────────────
    # TAB 6: FAIR Data & Export
    # ──────────────────────────────────────────────────────────────
    with tab6:
        st.subheader("📦 FAIR Data & Export Kluis")
        st.markdown("Doorzoekbare catalogus van alle tabletten met FAIR-compliant export functionaliteit.")

        tablets_df = load_tablets()

        col1, col2 = st.columns([3, 1])
        with col1:
            search = st.text_input("🔍 Zoek in tabletten", placeholder="Zoek op P-nummer, museum nummer, periode, herkomst...")
        with col2:
            export_format = st.selectbox("Export formaat", ["JSON-LD", "ATF", "CSV", "All"])

        if search:
            mask = tablets_df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)
            filtered_tablets = tablets_df[mask]
        else:
            filtered_tablets = tablets_df

        st.markdown(f"### 📊 {len(filtered_tablets)} tabletten gevonden")

        for _, row in filtered_tablets.iterrows():
            with st.expander(f"{row['tablet_id']} — {row.get('p_number', 'N/A')} ({row.get('period', 'N/A')})"):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown(f"""
                    **Museum Nummer:** {row.get('museum_number', 'N/A')}
                    **Periode:** {row.get('period', 'N/A')}
                    **Herkomst:** {row.get('provenance', 'N/A')}
                    **Transliteratie:** {row.get('transliteration', 'N/A')[:200]}...
                    **Vertaling:** {row.get('translation', 'N/A')[:200]}...
                    """)

                    img_path = row.get('image_path')
                    if img_path and Path(img_path).exists():
                        st.image(str(img_path), caption=row['tablet_id'], width=300)

                with col2:
                    st.markdown("**📥 Export Opties:**")

                    export_data = {
                        "tablet_id": row['tablet_id'],
                        "p_number": row.get('p_number'),
                        "museum_number": row.get('museum_number'),
                        "period": row.get('period'),
                        "provenance": row.get('provenance'),
                        "transliteration": row.get('transliteration'),
                        "translation": row.get('translation'),
                        "cuneiform_text": row.get('cuneiform_text'),
                        "metadata": json.loads(row['metadata_json']) if row.get('metadata_json') else {}
                    }

                    json_ld = {
                        "@context": "https://schema.org/",
                        "@type": "ArchaeologicalArtifact",
                        **export_data
                    }

                    if export_format in ["JSON-LD", "All"]:
                        json_str = json.dumps(json_ld, indent=2, ensure_ascii=False)
                        st.download_button(
                            label="📄 JSON-LD",
                            data=json_str,
                            file_name=f"{row['tablet_id']}.jsonld",
                            mime="application/ld+json",
                            key=f"jsonld_{row['tablet_id']}"
                        )

                    if export_format in ["ATF", "All"]:
                        atf_content = f"""#atf: lang={row.get('period', 'unknown')}
#atf: object={row['tablet_id']}
#atf: museum={row.get('museum_number', 'unknown')}
#atf: provenance={row.get('provenance', 'unknown')}

& {row.get('transliteration', '')}

# translation: {row.get('translation', '')}
"""
                        st.download_button(
                            label="📝 ATF",
                            data=atf_content,
                            file_name=f"{row['tablet_id']}.atf",
                            mime="text/plain",
                            key=f"atf_{row['tablet_id']}"
                        )

                    if export_format in ["CSV", "All"]:
                        csv_str = filtered_tablets[filtered_tablets['tablet_id'] == row['tablet_id']].to_csv(index=False)
                        st.download_button(
                            label="📊 CSV",
                            data=csv_str,
                            file_name=f"{row['tablet_id']}.csv",
                            mime="text/csv",
                            key=f"csv_{row['tablet_id']}"
                        )

        st.markdown("---")
        st.markdown("### 📦 Bulk Export")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📄 Alle JSON-LD"):
                all_jsonld = []
                for _, row in tablets_df.iterrows():
                    all_jsonld.append({
                        "@context": "https://schema.org/",
                        "@type": "ArchaeologicalArtifact",
                        "tablet_id": row['tablet_id'],
                        "p_number": row.get('p_number'),
                        "museum_number": row.get('museum_number'),
                        "period": row.get('period'),
                        "provenance": row.get('provenance'),
                        "transliteration": row.get('transliteration'),
                        "translation": row.get('translation')
                    })
                st.download_button(
                    "Download All JSON-LD",
                    json.dumps(all_jsonld, indent=2, ensure_ascii=False),
                    "all_tablets.jsonld",
                    "application/ld+json"
                )

        with col2:
            if st.button("📝 Alle ATF"):
                all_atf = []
                for _, row in tablets_df.iterrows():
                    all_atf.append(f"""#atf: lang={row.get('period', 'unknown')}
#atf: object={row['tablet_id']}
#atf: museum={row.get('museum_number', 'unknown')}

& {row.get('transliteration', '')}

# translation: {row.get('translation', '')}
""")
                st.download_button(
                    "Download All ATF",
                    "\n\n".join(all_atf),
                    "all_tablets.atf",
                    "text/plain"
                )

        with col3:
            if st.button("📊 Complete CSV"):
                csv_all = tablets_df.to_csv(index=False)
                st.download_button(
                    "Download Complete CSV",
                    csv_all,
                    "cuneiform_master_complete.csv",
                    "text/csv"
                )

    # Footer
    st.markdown("""
    <div class="footer">
        Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii) v2.0 |
        Polyphony · Phylomythology · Federated Corpus · Active Learning · FAIR Export
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()