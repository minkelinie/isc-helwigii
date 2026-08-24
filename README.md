# I.S.C. Helwigii — Cuneiform Analysis Platform

**Invitatio Scripta Cuneiformis Helwigii**  
*A Classical Frontispiece for Digital Assyriology*

---

## Overview

I.S.C. Helwigii is a comprehensive cuneiform analysis platform combining classical book-cover aesthetics with modern NLP/ML pipelines. It provides:

- **Classical Frontispiece UI** — 3D page-flip animation, Latin inscriptions, scholarly apparatus
- **Polyphony Engine** — 249 cuneiform signs with Bayesian disambiguation (Dirichlet priors), compound sign decomposition
- **Neural & Visual Embeddings** — SBERT (384-dim) text embeddings + ORB/BoVW (256-dim) visual features with FAISS indexing
- **Phylomythology** — Hierarchical clustering (UPGMA), maximum parsimony phylogeny of 23 myth texts across 26 archetypal motifs
- **Federated Corpus Registry** — 8+ sources (CDLI, ETCSL, ORACC, DCCLT, BDTNS, MIDDLE, RIAO, USER_FRAGMENTS) with streaming index
- **Active Learning Loop** — Human-in-the-loop corrections with automatic model retraining triggers
- **FAIR Export** — JSON-LD (schema.org), ATF (CDLI standard), CSV bulk export
- **6-Tab Streamlit Dashboard** — Codex, Corpus, Signs, Mythology, Active Learning, Export

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        STREAMLIT DASHBOARD                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ CODEX   │ │ CORPUS  │ │ SIGNS   │ │ MYTHOLOGY│ │ ACTIVE  │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│                              ┌─────────┐                         │
│                              │ EXPORT  │                         │
│                              └─────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   BACKEND CORE    │
                    │  (Database Pool,  │
                    │   FAISS Manager,  │
                    │   Active Learning │
                    │    Bayesian)      │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  POLYPHONY    │    │  PREBAKED     │    │  CORPUS       │
│  ENGINE       │    │  EMBEDDINGS   │    │  REGISTRY     │
│  (n-grams,    │    │  (SBERT +     │    │  (8 sources,  │
│   Bayesian,   │    │   ORB/BoVW,   │    │   streaming)  │
│   compounds)  │    │   FAISS)      │    │               │
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## Quick Start

### Docker (Recommended)

```bash
# Build and run
docker-compose up --build -d

# Access dashboard
open http://localhost:8501
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run pipeline (one-time setup)
python train_polyphony_engine.py
python precompute_global_embeddings.py
python -m phylomythology_engine
python sign_detection_engine.py

# Start dashboard
streamlit run app.py --server.port 8501
```

---

## Pipeline Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `train_polyphony_engine.py` | Build n-gram co-occurrence matrices, Bayesian priors, compound signs | `cuneiform_polyphony.json` |
| `precompute_global_embeddings.py` | Compute SBERT/TF-IDF text embeddings + ORB/BoVW visual features + FAISS index | `prebaked_embeddings/`, `prebaked_sign_knowledge` table |
| `phylomythology_engine.py` | UPGMA clustering, maximum parsimony phylogeny of 23 myths | `phylo_tree` table, `myth_evolution_tree.png` |
| `sign_detection_engine.py` | ORB+BoVW sign detection on tablet images | 2219+ detected signs, stroke analysis |
| `corpus_registry.py` | Federated corpus indexing from 8 sources | `corpus_catalog` table |

---

## Data Model (SQLite)

**Core Tables:**
- `tablets` — 1,218+ tablets from CDLI with transliterations
- `cuneiform_signs` — 1,847+ individual sign occurrences with bounding boxes
- `myth_texts` — 23 major Sumerian/Akkadian myth compositions
- `motif_taxonomy` — 26 archetypal motifs (S1–S8 categories)
- `motif_instances` — 166 motif occurrences in myth texts
- `phylo_tree` — 45 phylogenetic tree nodes
- `corpus_catalog` — 321 entries from 3 federated sources
- `polyphony_corrections` — Active learning correction log
- `prebaked_embeddings` — Neural/visual embeddings for fast similarity
- `prebaked_sign_knowledge` — 249 sign knowledge base entries

---

## Key Features

### Polyphony Engine
- **N-gram Co-occurrence**: Bigram/trigram matrices from 1,847 sign tokens
- **Bayesian Disambiguation**: Dirichlet-smoothed P(reading \| context)
- **Compound Signs**: 15 multi-sign compounds with decomposition rules
- **28 Context Rules**: Positional and collocational disambiguation patterns

### Visual Analysis
- **ORB Descriptors**: 500 features per image, rotation/scale invariant
- **BoVW (256-dim)**: K-means vocabulary for visual similarity
- **Stroke Classification**: 5 stroke types (wedge, vertical, horizontal, diagonal, curve)
- **Sign Detection**: 2,219+ signs detected across tablet corpus

### Phylomythology
- **23 Myth Texts**: Atrahasis, Enuma Elish, Gilgamesh, Inanna's Descent, etc.
- **26 Archetypal Motifs**: Chaoskampf, Flood, Divine Council, Hero's Journey, etc.
- **UPGMA Clustering**: Hierarchical grouping of myth traditions
- **Maximum Parsimony**: Phylogenetic tree with 45 nodes

---

## API Reference (BackendCore)

```python
from backend_core import BackendCore, BackendConfig

config = BackendConfig(db_path="/data/cuneiform_master.db")
backend = BackendCore(config)

# Corpus search
results = backend.search_corpus("gilgamesh flood", k=10)

# Sign disambiguation
readings = backend.disambiguate_sequence(["AN", "KI", "LUGAL"])

# Active learning
backend.submit_correction("AN", "SUM:an", "SUM:ana", "context", "scholar")

# Embeddings
embeddings = backend.get_embeddings(entry_ids=[1,2,3], entry_type="tablet")
```

---

## Export Formats

### JSON-LD (schema.org)
```json
{
  "@context": "https://schema.org/",
  "@type": "Corpus",
  "name": "I.S.C. Helwigii Corpus",
  "description": "Federated cuneiform corpus with polyphonic analysis",
  "hasPart": [...]
}
```

### ATF (CDLI Standard)
```atf
&header
object = tablet
provenance = Nippur
period = Old Babylonian
&text
1. dumu AN.KI
2. lugal-gal
```

### CSV Bulk
```csv
id,source,transliteration,translation,period,museum_number
1,CDLI,"dumu an.ki","The child of An and Ki","Old Babylonian","P252048"
```

---

## Requirements

- Python 3.11+
- SQLite 3.35+
- FAISS (faiss-cpu)
- sentence-transformers (optional, falls back to TF-IDF+SVD)
- OpenCV (headless)
- Streamlit 1.35+
- scikit-learn, numpy, pandas, plotly, networkx, tqdm, Pillow, pyyaml, requests

---

## License

Academic Research — SignumCore ISMS Project

---

## Citation

```
@software{isc_helwigii_v2,
  author = {Mink Helwig},
  title = {I.S.C. Helwigii — Cuneiform Analysis Platform v2.0.0},
  year = {2026},
  note = {Academic Production Release — Classical Frontispiece Edition}
}
```

---

*Aperi Codicem — Open the Codex*