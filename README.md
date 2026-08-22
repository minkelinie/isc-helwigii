# 🏛️ OX-Stealth Myth Hunter

[![CI](https://github.com/SignumCore/ox-stealth-myth-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/SignumCore/ox-stealth-myth-hunter/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/SignumCore/ox-stealth-myth-hunter/branch/main/graph/badge.svg)](https://codecov.io/gh/SignumCore/ox-stealth-myth-hunter)
[![License: CC-BY-4.0](https://img.shields.io/badge/License-CC--BY--4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://hub.docker.com/r/signumcore/ox-stealth)

> **Digital Humanities Pipeline** voor spijkerschrift: van ruwe tabletten → genormaliseerde transliteraties → AI-gedreven motief/entiteit extractie → kennisgraaf → interactieve dashboards → citeerbare publicatie (Zenodo DOI).

## ✨ Features

- **Multi-bron ingestie**: CuneiML (Zenodo), HuggingFace Datasets, CDLI (extensieerbaar)
- **ORACC-normalisatie**: Unicode → ASCII, canonieke tekenconventies
- **LLM-gestuurde analyse**: Few-shot `meta-llama/llama-3.1-70b-instruct` via OpenRouter voor lemmatisatie, taaldetectie, motieven, entiteiten
- **Cross-linguale alignement**: SBERT embeddings (multilingual) → cosine similarity ≥ 0.78
- **Thematische clustering**: Greedy/HDBSCAN op embedding-ruimte
- **Kennisgraaf export**: GraphML, Neo4j Cypher, Cytoscape.js
- **Publicatie-klaar**: Static HTML dashboard, Streamlit app, DataCite/Zenodo metadata
- **Productie-hardening**: Ruff, Black, MyPy, Bandit, Pytest, Pre-commit, GitHub Actions CI/CD

## 📊 Resultaten (voorbeeld)

| Metric | Waarde |
|--------|--------|
| Tabletten in corpus | ~500+ |
| Genormaliseerde transliteraties | ~480 |
| Gemiddelde LLM confidence | 0.87 |
| Cross-linguale alignementen | ~1.200 |
| Thematische clusters | 12–15 |
| Entiteiten (uniek) | ~350 |

## 🏗️ Architectuur

```mermaid
graph LR
    A[Raw Sources] --> B[Ingestion Pipeline]
    B --> C[SQLite: cuneiform_master.db]
    C --> D[Normalization Engine]
    D --> E[ORACC + LLM Annotations]
    E --> F[Myth Hunter]
    F --> G[Embeddings + Clustering]
    G --> H[Knowledge Graph]
    H --> I[Static HTML Dashboard]
    H --> J[Streamlit App]
    H --> K[Zenodo Publication]
```

## 📖 Documentatie

👉 **[https://signumcore.github.io/ox-stealth-myth-hunter/](https://signumcore.github.io/ox-stealth-myth-hunter/)**

## 🤝 Bijdragen

Zie [CONTRIBUTING.md](CONTRIBUTING.md) — we volgen Conventional Commits & DCO.

## 📄 Licentie

CC-BY-4.0 — vrij te gebruiken, aanpassen, delen met attributie.