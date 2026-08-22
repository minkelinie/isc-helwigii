# OX-Stealth Myth Hunter

**Multi-lingual Cuneiform Corpus Pipeline** voor Digital Humanities research.

## 🎯 Wat doet het?

De pipeline transformeert ruwe spijkerschriftdata (Sumerisch, Akkadisch, Hethitisch) naar een **onderzoeksklare, geciteerbare dataset** met:

| Stap | Output |
|------|--------|
| **1. Ingestion** | `cuneiform_master.db` — SQLite met ruwe tabletten (CuneiML, HuggingFace, CDLI) |
| **2. Normalisatie** | ORACC-transliteraties, taaldetectie, LLM-lemmatisatie |
| **3. Myth Hunter** | Motieven, entiteiten, SBERT embeddings, cross-linguale alignementen, clusters |
| **4. Kennisgraaf** | GraphML, Neo4j Cypher, Cytoscape.js JSON |
| **5. Dashboards** | Static HTML (publicatie-klaar), Streamlit (interactief), DataCite metadata |

## 🚀 Quickstart

```bash
# 1. Clone & dependencies
git clone https://github.com/SignumCore/ox-stealth-myth-hunter
cd ox-stealth-myth-hunter
pip install -e ".[dev]"

# 2. Draai volledige pipeline (in Docker container met /data volume)
python run_me.py       # Ingestion
python run_me_2.py     # Normalisatie
python run_me_3.py     # Myth Hunter
python run_me_4.py     # Dashboards & Export

# 3. Bekijk resultaten
open export/dashboard/index.html          # Static HTML
# OF
streamlit run export/dashboard/app.py     # Live dashboard
```

## 📦 Docker

```dockerfile
# Dockerfile (in repo root)
FROM python:3.10-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e ".[dev]"
COPY . .
VOLUME /data
CMD ["python", "run_me.py"]
```

```bash
docker build -t ox-stealth .
docker run -v ~/Desktop/OxStealthData:/data -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY ox-stealth
```

## 📚 Documentatie

- [Architecture Overview](architecture/overview.md)
- [Database Schema](architecture/schema.md)
- [Pipeline Stages](architecture/pipeline.md)
- [API Reference](api.md)
- [Dashboard Guide](dashboard.md)
- [Publishing to Zenodo](publishing.md)

---

*Licentie: CC-BY-4.0 — © 2026 Mink Helwig / SignumCore*