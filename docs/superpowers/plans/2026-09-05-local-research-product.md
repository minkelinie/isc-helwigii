# Local research product implementation plan

**Goal:** A usable offline, single-researcher workbench covering the complete evidence-to-hypothesis workflow, with an explicit capability and validation register.

**Architecture:** Python modular monolith, SQLite project file, Streamlit interface. Immutable source snapshots, editions, annotations, review events and experiment records form the public application API. Media stays in the project database for portable backups. Scientific methods are versioned baselines; manual expert work is supported independently of automation.

**Tech stack:** Python 3.11+, standard-library research core, optional Streamlit UI, pytest, Ruff, GitHub Actions.

**Spec:** `docs/plans/2026-09-04-evidence-first-foundation-design.md`, amended by the owner's requirement that the entire product run locally. PostgreSQL and hosted services are not prerequisites.

## What “complete” means

Workflow coverage and scientific validity are separate acceptance criteria. This release must allow a researcher to import evidence, inspect it, record interpretations, review them, compare witnesses and measurements, test exploratory hypotheses, evaluate predictions and export a reproducible project without a network connection. Perfect automatic translation, automatic 3D joins, calibrated geographic origin and prehistoric ancestral dating are research programmes requiring measured data and external expert validation; they cannot be declared achieved by adding interface tabs.

## Product stages and acceptance

1. **Reproducible local foundation:** clean GitHub-based branch, small installable package, deterministic project paths, CI. Port only the 25 foundation files; keep historical datasets out of new commits.
2. **Evidence store:** transactional schema initialization that rejects unrelated databases; immutable raw snapshots and source-specific editions; stable identities; searchable artifact dossiers. Repeat import is idempotent; conflicting editions coexist.
3. **Import/export:** native research JSON, CDLI-style ATF and ORACC catalogue JSON, preserving raw bytes and licenses; media with checksums; SQLite backup bundles verified before restore to a new path. Invalid imports roll back in full.
4. **Reading and review:** passage-anchored transliteration, translations, linguistic analysis, categories, motifs, date and place claims. Alternatives coexist. Explicit actor, evidence, origin and append-only accept/reject decisions; revisions supersede only compatible annotations.
5. **Text matching and translation assistance:** conservative Unicode tokenization, Jaccard and sequence baselines, aligned differences, retrieval of accepted translations with sources and abstention. No generated translation is presented as an attestation.
6. **Material comparison and joins:** structured lab measurements including method, laboratory, unit, uncertainty, calibration and reference group; compare only matching methods/calibrations/units and common analytes. Save manual physical join evidence, image regions and counter-evidence. Scores describe similarity, never origin probabilities.
7. **Myth and hypothesis lab:** passage motifs, witness networks, explicit absence/unknown distinction, alternate inheritance/diffusion/convergence explanations, date interval compatibility. Export exact inputs and method version for each run. No arbitrary bootstrap or ancestor dates.
8. **Evaluation:** family-grouped train/dev/test splitting, no family or exact duplicate leakage, classification/retrieval metrics with abstentions and sample counts. Cards record scope, inputs, limitations and the difference between software tests and scientific benchmarks.
9. **Local interface and CLI:** initialize/demo/import/list/annotate/review/run/export/restore/start workflows; locally bound Streamlit app with dossier, reading, comparison, material, hypothesis, registry and backup pages. No telemetry or external model calls.
10. **Delivery:** full integration tests, installed-wheel workflow, Streamlit AppTest, container configuration, user guide, capability matrix, clean Git/LFS diff, push and PR using existing authorization. Real-corpus/model/expert validation gaps remain explicitly open.

## File and interface map

- `store.py`: `ResearchStore(path)`, `initialize()`, `import_records(raw, records, source, license)`, `artifacts(query)`, `dossier(id)`, `annotate(...)`, `review(...)`, `save_run(...)`, `add_asset(...)`. All writes transactional; existing evidence cannot be updated or deleted through SQL.
- `ingest.py`: `parse_native(raw)`, `parse_atf(raw)`, `parse_oracc(raw)` -> normalized records retaining external IDs, original metadata and language.
- `analysis.py`: `text_similarity(a,b)`, `rank_parallels(query,records,language)`, `translation_memory(...)`, `compare_materials(a,b)`, `motif_network(witnesses)`, `date_overlap(a,b)`. Missing information causes abstention, not invented values.
- `evaluation.py`: `grouped_split(records,seed)`, `evaluate_labels(gold,predicted)` with strict IDs and grouped duplicates.
- `bundles.py`: `export_bundle(store,destination)`, `restore_bundle(bundle,destination)` with SHA-256 and schema validation; no archive path extraction.
- `demo.py`: unmistakably synthetic three-witness dataset and demonstration annotations.
- `ui.py`: task-based local Streamlit workbench calling public core interfaces.
- `cli.py`: expose local project lifecycle and research operations; clear nonzero error codes.
- `tests/test_research_store.py`, `test_ingest.py`, `test_analysis.py`, `test_evaluation.py`, `test_bundles.py`, `test_research_cli.py`, `test_ui.py`: behavior and end-to-end regression contracts.

## Execution batches

- [x] Batch A: write failing store/import tests; implement schema and adapters; verify rollback, idempotency, immutable evidence, revision/review contracts and raw retention.
- [x] Batch B: write failing analysis/evaluation tests; implement reproducible baselines and abstention; verify language separation, unit checks, unknown motifs, duplicate leakage and empty metrics.
- [x] Batch C: write failing backup/CLI tests; implement bundles and research commands; verify export/restore equivalence and tamper refusal; run installed package contract.
- [x] Batch D: implement local interface, synthetic demo, capability cards and guide; verify UI form interactions and full research lifecycle.
- [x] Batch E: review all capability claims against observed behavior; run quality gates; record limitations and verification; commit, push and open PR #1. This completes the local alpha delivery, not the research validation backlog below.

## Required behavior examples

```python
store = ResearchStore(tmp_path / 'research.db')
store.initialize()
first = store.import_records(raw, records, source='local', license='private')
assert store.import_records(raw, records, source='local', license='private') == first
assert len(store.artifacts()) == len(records)
assert store.dossier(store.artifacts()[0]['id'])['editions'][0]['snapshot_id'] == first
```

```python
assert text_similarity('a b', 'a b')['jaccard'] == 1.0
assert compare_materials(sample_xrf, sample_inAA)['status'] == 'abstained'
assert motif_network([{'id':'A','motifs':None}])['edges'] == []
```

Commands run from the selected worktree with `rtk`: `.venv/bin/python -m pytest -q`, `ruff check src tests scripts`, `python scripts/check_docs.py`, `python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .`, `python scripts/check_wheel.py dist/isc_helwigii-2.0.0-py3-none-any.whl`.

## Research validation backlog (not satisfied by this software release)

- Licensed Akkadian and Sumerian expert gold sets across period, genre, damage and composition family.
- OCR/segmentation and polyphony model evaluation, local CPU/GPU model packaging and hardware benchmarks.
- Translation evaluation by Assyriologists, context conditioning and calibrated abstention.
- Metric 3D acquisition, positive/negative fragment joins and registration calibration.
- Laboratory/reference clay populations, instrument harmonization and provenance validation.
- Independently annotated motif definitions, phylogenetic/network model comparison, real resampling, preservation-bias simulations and prehistoric dating sensitivity.
- Full ORACC CDL linguistic adapter, eBL and museum licensing/access, legacy corpus promotion after source audit.
- Multi-project collaboration, accessibility and sustained large-corpus performance testing on Windows/Linux/macOS.

Primary adapter references: https://oracc.museum.upenn.edu/doc/opendata/json/index.html and https://cdli.earth/docs/api . Licenses are supplied for each import, never assumed from the hosting platform.
