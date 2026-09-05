# Changelog

## Unreleased — local research workbench, 2026-09-05

- Added offline project lifecycle, immutable evidence and edition history, reviewable passage annotations, images and report attachments.
- Added native JSON, ATF, ORACC catalogue and read-only legacy SQLite imports.
- Added exploratory textual/material/motif/chronology methods, exact reviewed translation memory, classification evaluation and family-grouped splits.
- Added reproducible experiment records, verified project bundles and locally bound Streamlit research workspaces.
- Hardened evidence replacement, schema/backup integrity, translation revision scope and missing-language abstention after independent code review.
- Reduced base installation to Python standard-library dependencies; the UI is an optional extra.
- Scientific OCR, trained translation, 3D joins, calibrated material provenance and prehistoric inference remain open research work, not release claims.

> Historical entries below record what earlier releases claimed. The evidence-first audit found that several 2.0.0 capabilities were demonstrations, placeholders, unconnected models, or absent CI. They are not validation statements. The foundation work reports only behavior covered by current tests and artifact checks.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-08-23

### 🎉 Major Release — I.S.C. Helwigii Rebrand & Feature Complete

**Rebranded from "OX-Stealth Myth Hunter" to "Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii)"**

### ✨ Added

#### Core Platform
- **6-tab Streamlit Dashboard**: Fragment Matcher, Phylomythology, Sign Detector, Polyphony Engine, User Dataset Import, FAIR Export
- **Federated Corpus Registry** (`corpus_registry.py`): CDLI (200), ORACC (100), ETCSL (21), BDTNS, RINAP, RIMB, DCCLT, GEM — 321 total entries, streaming index
- **Polyphony Engine** (`polyphony_engine.py`): 10 core signs with Sumerian/Akkadian readings, logographic values, context disambiguation rules, compound signs
- **Active Learning Loop**: User corrections saved to DB → applied to in-memory catalog → pending review queue with apply/discard
- **User Dataset Import** (Tab 5): Pluggable import for JPG/PNG/TIFF images, CSV metadata, ZIP archives, ATF texts

#### Phylomythology Pipeline
- **23 myth texts** loaded (Gilgamesh, Enuma Elish, Atrahasis, Etana, Adapa, etc.)
- **26 archetypal motifs** across 8 archetypes: FLOOD_NARRATIVE, DIVINE_COUNCIL, HERO_JOURNEY, IMMORTALITY_QUEST, CREATION, CIVILIZATION, AFTERLIFE, CHAOSKAMPF
- **166 motif instances** extracted with position tracking
- **253 pairwise Jaccard-Cosine distances** computed
- **45-node phylogenetic tree** (UPGMA + maximum parsimony)
- **174 motif migrations** traced (gain/loss/modification/convergence)

#### Sign Detection Pipeline
- **2,219+ signs detected** across 4 tablets via ORB + BoVW + contour analysis
- **5 sign types**: wedge, vertical, horizontal, angled, complex
- **Confidence scoring** with spatial bounding boxes

#### Fragment Matcher
- HSV terracotta segmentation + morphological cleanup
- Contour detection + Douglas-Peucker simplification
- Fracture analysis via convexity defects
- Wedge classification by HoughLinesP angle
- **Join-Confidence Index (JCI)**: 30% visual + 50% semantic + 20% n-gram

#### FAIR Export (Tab 6)
- **JSON-LD** (schema.org/ArchaeologicalArtifact)
- **ATF** (CDLI standard format)
- **CSV** (bulk and per-tablet)
- Per-tablet and bulk download

#### Deployment & DevOps
- **Dockerfile**: python:3.11-slim + headless OpenCV deps
- **docker-compose.yml**: App + optional corpus-sync service
- **GitHub Actions CI/CD**: Ruff, Black, MyPy, Bandit, Pytest, Docker build/push
- **pyproject.toml**: Modern packaging with entry points
- **Health checks**: `/_stcore/health` endpoint

### 🔧 Changed
- Database schema extended: `polyphony_corrections`, `user_datasets`, `user_fragments`, `corpus_catalog` tables
- Streamlit caching: `@st.cache_resource` for DB connections, `@st.cache_data` for queries
- OpenCV headless compatibility in Docker (libglib2.0-0, libsm6, libxext6, libxrender-dev, libxcb1, libgl1)

### 📊 Metrics
| Component | Count |
|-----------|-------|
| Core polyphonic signs | 10 |
| Context disambiguation rules | 4 |
| Compound signs | 3 |
| User correction capacity | Unlimited (SQLite) |
| Federated corpus entries | 321 |
| Corpus sources | 8 (3 populated) |

---

## [1.0.0] - 2026-08-15

### Initial Release — OX-Stealth Myth Hunter
- CDLI ingestion pipeline (12 tablets)
- Sign detection engine (ORB + BoVW)
- Phylomythology engine (myth texts, motifs, phylogeny)
- 4-tab Streamlit dashboard
- SQLite database with all pipeline data
- Docker deployment

---

## [Unreleased]

### Evidence-first foundation

- Added an installable `isc_helwigii` package with one valid console entrypoint.
- Added deterministic environment-driven runtime paths.
- Added read-only database health inspection with explicit legacy schema recognition.
- Added focused tests, wheel isolation checks, and GitHub Actions configuration.
- Defined repository boundaries for source, data, models, and generated evidence.
- Replaced stale setup instructions and marked legacy scientific claims as unvalidated.
