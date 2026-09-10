# I.S.C. Helwigii

A local cuneiform research workbench for collecting evidence, annotating passages, reviewing interpretations, comparing witnesses and measurements, and exporting reproducible experiments.

This is an **alpha research workbench**. Translation assistance currently retrieves reviewed exact parallel passages. Text and material comparisons and motif networks are exploratory baselines. Automatic sign recognition, trained translation, geometric 3D joins and validated prehistoric ancestry/dating are not included. The application shows this distinction in its capability register.

## Start locally

Python 3.11 or newer is required. The research core uses only the standard library; the interface is an optional dependency. Installation needs internet access once; project workflows subsequently run offline.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ui]"
isc-helwigii init ./research.db
isc-helwigii demo ./research.db
isc-helwigii start ./research.db
```

On Windows, activate with `.venv\Scripts\Activate.ps1` and use `python` instead of `python3`. Windows is a target platform; this version has not yet received a Windows runtime test.

Open http://127.0.0.1:8501 . The server binds to this computer, telemetry is disabled, and no external model is contacted. The three demonstration witnesses are synthetic and visibly labelled. Use a separate project for real research.

## Research workflows

- **Project:** native research JSON, CDLI-style ATF and ORACC catalogue imports; raw source bytes, SHA-256 and rights statements.
- **Research dossier:** select a source passage and retrieve same-language text candidates across the complete corpus, with shared/different tokens, source editions, reviewed exact translations and a saved experiment.
- **Tablets:** source-specific identities, multiple editions, conflicting source fields, attached images/reports/files and source downloads.
- **Reading:** passage-anchored transliteration, translation, morphology notes, sign regions, motifs, categories, dates and places; alternative interpretations and append-only review.
- **Translation workspace:** select an exact source passage, propose and review a translation, inspect uncovered spans and overlapping alternatives, and export an edition-specific worksheet as Markdown or JSON. Coverage measures editorial completion, not accuracy.
- **Comparison:** same-language lexical overlap and token alignment; manual physical-join proposals with evidence.
- **Materials:** laboratory, method, calibration, reference group, analytes, units and one-sigma uncertainty; component-wise compatible measurement distances.
- **Myths:** reviewed passage motifs, undirected overlap networks, witness date intervals, competing explanations and falsifiable hypothesis records.
- **Evaluation:** classification with abstention, composition-family/exact-duplicate grouped splits, counts and confusion matrices.
- **Corpus quality:** deterministic source and metadata inventory, bounded issue queue and evidence-linked reference-set preparation without changing the project.
- **Experiments and export:** frozen inputs, output, actor, method implementation source and checksum; portable verified project bundles including media.

Review identities are locally entered attribution, not authenticated roles. Accepted annotations are editorial decisions, not automatic scientific validation. Missing data causes abstention. An overlap score is not an ancestry, join or geographic-origin probability.

## Audit and reference preparation

In the interface, open **Onderzoeksdossier**, select a tablet and leave the complete text or paste an exact passage from it. If a passage occurs more than once, select the intended occurrence. Click **Onderzoeksdossier voorbereiden**. Results persist while you inspect the same selection and are saved under **Experimenten & export**.

The CLI offers the same operation without a request file:

```bash
isc-helwigii prepare ./research.db EDITION_ID --actor researcher --target-language nl --limit 10
isc-helwigii prepare ./research.db EDITION_ID --actor researcher --start 0 --end 40
```

Ranking compares NFC/casefold token sets with full same-language editions using Jaccard overlap, with ties ordered by edition ID. Other editions of the selected artifact are excluded. This is a lexical baseline, so short parallels inside long texts may rank poorly. It does not generate translations. A saved run records the source snapshot IDs, edition manifest checksum, passage, results and implementation; rerun after new sources or reviews.

Open **Vertalen** for the manual translation workflow. Source positions follow your exact passage selection; repeated passages require selecting the intended occurrence. Proposals remain pending until explicitly reviewed. Accepted overlapping spans remain conflicts; missing passages remain untranslated. The worksheet reads one consistent source/review snapshot without changing the project.

```bash
isc-helwigii translation-sheet research.db EDITION_ID --target-language nl
isc-helwigii translation-sheet research.db EDITION_ID --format markdown --output translation.md
```

Without `--output`, the CLI prints the requested format (JSON by default). With `--output`, that file receives the requested format and standard output retains the JSON worksheet. Existing files are never overwritten by file export. Keep the JSON export alongside Markdown for the complete captured worksheet evidence; project bundles preserve the full review history.

```bash
isc-helwigii audit ./research.db
isc-helwigii audit ./research.db --output ./corpus-audit.json
isc-helwigii reference-set ./research.db --axis genre --seed 42 --output ./genre-reference.json
```

Exports require a new path and never overwrite an existing file or the project. The audit counts every edition, while tablet totals count distinct source-specific artifacts. Its metadata flags are prompts for editorial checking, not proof that a record is false, and recorded license text is not independent rights clearance.

A reference item needs a current accepted category annotation on the requested axis and one non-placeholder accepted `composition_family`. Record and review both in **Lezen & annoteren**; imported legacy labels are metadata only and are not promoted automatically. Pending, rejected, superseded, conflicting, synthetic, empty, wholly unreadable and unknown-language editions are excluded with reasons. Actor names record local attribution and do not authenticate expertise.

Exact-text grouping applies Unicode NFC, casefolding and whitespace collapse only. It preserves damage notation, diacritics and index digits. Editions of one artifact, accepted composition families and exact normalized duplicates are grouped transitively before exclusions, so excluded bridge records cannot introduce split leakage. The seed is deterministic for one corpus snapshot, but later corpus or review edits can move components; retain and compare the exported fingerprints.

## Import your data

```bash
isc-helwigii import ./research.db ./corpus.atf --format atf --source cdli-local-export --license "private research copy"
isc-helwigii import ./research.db ./catalogue.json --format oracc-catalogue --source oracc-project --license "record actual project terms"
isc-helwigii import-legacy ./research.db /path/to/legacy.db --source legacy-local --license private --limit 500
```

The legacy adapter reads a bounded `tablets` query without changing the original database. Original generated labels remain unreviewed metadata. ORACC support currently covers catalogue JSON, not full CDL linguistic editions. ATF support covers artifact headers, language, surface markers and numbered lines; unsupported ATF directives remain in raw source bytes.

## Backup and restore

```bash
isc-helwigii export ./research.db ./research.zip
isc-helwigii restore ./research.zip ./restored.db
```

Both operations require a new destination. Restore verifies archive and evidence checksums, schema guards, SQLite integrity and foreign keys. The zip includes original sources and media, so their usage rights still apply. The source of truth is the SQLite project; do not edit it directly.

Open, health and restore share the versioned table contract, including primary keys, mandatory fields, foreign keys, uniqueness, review decisions and immutable triggers. Supported tables must match the canonical versioned DDL (formatting whitespace outside quoted literals is ignored); hand-rebuilt schemas are not silently accepted merely because their column names match. Health also runs SQLite quick and foreign-key checks; complete evidence checksums are verified on export/restore.

## Tests and package verification

```bash
python -m pip install -e ".[dev,ui]"
python -m pytest -q
ruff check src tests scripts
python scripts/check_docs.py
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
python scripts/check_wheel.py dist/isc_helwigii-2.0.0-py3-none-any.whl
```

The wheel check installs without dependencies into a fresh environment and exercises project initialization, demo ingestion, export and restore. CI runs tests, UI interaction tests and wheel checks on Python 3.11/3.12. Version `2.0.0` is inherited package metadata, not a claim of scientific maturity.

## Optional container

```bash
docker compose config --quiet
docker compose up --build
```

The container initializes a new `/data/research.db` in its named volume and serves only host loopback port 8501. Container build/runtime must be checked with a working Docker daemon; successful Compose parsing alone does not verify the image.

## Documentation and roadmap

- [Local research guide](docs/local-research-guide.md)
- [Current software status](docs/status.md)
- [Product implementation plan and outstanding research validation](docs/superpowers/plans/2026-09-05-local-research-product.md)
- [Scientific design](docs/plans/2026-09-04-evidence-first-foundation-design.md)
- [Repository and artifact policy](docs/repository-policy.md)

Legacy root scripts remain historical experiments and are not the installed application. Code and small fixtures belong in Git; databases and model weights belong in local projects or separately governed artifact storage.

Existing license declarations conflict between CC-BY-4.0 and MIT. They have been preserved; a formal public release requires an explicit code/data/model licensing decision. This development branch does not relicense imported sources.
