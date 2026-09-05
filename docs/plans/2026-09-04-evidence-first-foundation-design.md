# ISC Helwigii — Evidence-first foundation design

**Status:** proposed for implementation
**Date:** 2026-09-04
**Branch:** `codex/evidence-first-foundation`
**Decision:** scientific rebuild while retaining useful components (Route B)

## 1. Purpose

ISC Helwigii will become a scientifically defensible research workbench for cuneiform. It will generate, compare, and review hypotheses for:

- sign recognition and transliteration;
- normalization, morphology, and translation;
- language, period, genre, archive, region, and motif classification;
- physical and textual fragment matching;
- material provenance of clay tablets;
- relationships among myth variants, including possible common ancestry and horizontal diffusion.

The system must never turn a model score into an unexplained historical fact. Every derived result remains connected to its evidence, method, version, uncertainty, and review history.

## 2. Initial scope

### Included

- Akkadian and Sumerian as the first measured language tracks.
- Versioned ingestion from CDLI and ORACC, followed by an eBL adapter where licensing and access permit it.
- A small, redistributable fixture corpus for tests and demonstrations.
- Existing local databases preserved as imported legacy snapshots, not treated as ground truth.
- A modular monolith: one Python package, one migration system, explicit domain modules, and a Streamlit research UI during the foundation phase.
- PostgreSQL as the intended shared research store; SQLite remains supported for fixtures, tests, and single-user demonstrations.

### Excluded from the foundation phase

- Claims of perfect translation.
- Automated publication of historical conclusions without expert review.
- Inferring clay chemistry from ordinary photographs.
- Treating synthetic or heuristic labels as gold data.
- A microservice migration before the domain boundaries and benchmarks are stable.
- Support claims for every language written in cuneiform before separate evaluation sets exist.

## 3. Design principles

1. **Evidence is immutable; interpretations are versioned.** Raw source records and source snapshots are append-only. Corrections create new annotations rather than overwriting observations.
2. **Observed, imported, inferred, and reviewed are distinct states.** The UI and exports must preserve that distinction.
3. **Each task has its own benchmark.** OCR, transliteration, translation, classification, physical joins, textual joins, provenance, and historical inference cannot share one generic accuracy score.
4. **Uncertainty is a product feature.** Top-k candidates, calibrated probabilities, abstention, missing evidence, and disagreement are displayed explicitly.
5. **No model without a model card and dataset card.** Cards record scope, licensing, splits, metrics, limitations, and known failure modes.
6. **No historical claim without a reproducible experiment.** Inputs, feature definitions, parameters, software version, random seed, and outputs are bundled.
7. **Human review is governed.** Proposed annotations stay pending until an authorized reviewer accepts, rejects, or supersedes them.
8. **Large artifacts do not live as accidental Git history.** Git stores code, schemas, manifests, checksums, and small fixtures; datasets and checkpoints use an artifact store or formal release mechanism.

## 4. Target architecture

```text
CDLI / ORACC / eBL / museum & lab data
                  |
          versioned source adapters
                  |
          immutable evidence store
        /          |             \
 text pipeline  material data  image/3D pipeline
        \          |             /
       versioned claims and candidate matches
                  |
       expert review + benchmark registry
                  |
      hypothesis experiments / knowledge graph
                  |
        research UI, API, and exports
```

The initial implementation is a modular monolith with dependency boundaries enforced in Python. This keeps local research use simple while allowing later extraction of compute-heavy workers.

### Proposed package layout

```text
src/isc_helwigii/
  config/          environment and typed settings
  db/              models, repositories, migrations
  domain/          evidence, claims, review, identifiers
  ingest/          source adapters and snapshot manifests
  language/        signs, transliteration, morphology, translation
  matching/        physical, textual, and provenance candidates
  mythology/       motif assertions, witnesses, hypothesis models
  evaluation/      datasets, metrics, calibration, error analysis
  experiments/     reproducible run bundles
  api/             stable application interface
  ui/              Streamlit research interface
```

Top-level scripts become thin console adapters or are retired. Runtime modules never depend on a developer-specific desktop path.

## 5. Canonical evidence model

### Source and artifact entities

- `source_system`: corpus or institution, license, terms, base URI.
- `source_snapshot`: source version, retrieval time, checksum, adapter version.
- `artifact`: persistent external identifiers, collection, museum number, object type.
- `artifact_assertion`: imported or reviewed claims such as period, provenience, excavation context, dimensions, and language.
- `media_asset`: image, RTI, 3D mesh, hand copy, rights, capture metadata, checksum.
- `material_sample`: sampling method, instrument, calibration, laboratory, uncertainty, elemental/mineralogical measurements, and reference group.

### Text entities

- `inscription`: a versioned edition attached to an artifact.
- `witness`: the relationship between an artifact inscription and a reconstructed composition.
- `text_line` and `text_segment`: source order and damaged/lost spans.
- `sign_observation`: bounding geometry or textual position, observed glyph, and media link.
- `sign_candidate`: ranked sign identity produced by a person or model.
- `transliteration_annotation`: reading with language, period convention, segmentation, author, and evidence.
- `linguistic_annotation`: normalization, lemma, morphology, syntax, and named entities.
- `translation_annotation`: target language, passage alignment, alternatives, citations, and review state.

### Research entities

- `motif_definition`: versioned scholarly definition and ontology links.
- `motif_assertion`: a bounded passage, role/event structure, annotator or model, confidence, and review.
- `match_candidate`: match type, feature-level evidence, component scores, calibration version, and status.
- `hypothesis`: a testable statement with priors, assumptions, evidence selection, and competing explanations.
- `experiment_run`: code/data/model versions, parameters, seeds, logs, outputs, and metrics.
- `review_event`: append-only accept, reject, revise, or supersede action.

Every assertion uses stable identifiers and contains `origin_type` (`imported`, `observed`, `inferred`, or `reviewed`).

## 6. Ingestion and data governance

Each adapter follows the same contract:

1. fetch or receive a named source version;
2. save the raw response and checksum;
3. validate source-specific schema;
4. map without discarding original identifiers or fields;
5. record licenses and attribution;
6. deduplicate by explicit crosswalks, never title similarity alone;
7. produce a quality report with missingness, conflicts, and rejected records;
8. make the import idempotent for a given snapshot and adapter version.

Conflicting dates, languages, proveniences, or readings remain separate assertions. A resolver may select a preferred display value, but it cannot erase the disagreement.

## 7. Language pipeline

The language pipeline consists of separately evaluated stages:

1. media preprocessing and tablet/line segmentation;
2. sign localization and top-k sign classification;
3. sign sequence ordering;
4. transliteration and word segmentation;
5. language, dialect, and period conditioning;
6. morphological and syntactic analysis;
7. aligned translation with alternatives and supporting parallels.

### Evaluation rules

- Splits occur by artifact and composition family, not generated example.
- Near-duplicate editions and fragments are grouped before splitting.
- Results are stratified by language, period, genre, damage level, sign frequency, and source corpus.
- Polyphonic signs receive a dedicated gold benchmark with contextually attested readings.
- Translation uses automatic metrics plus expert adequacy, faithfulness, uncertainty, and terminology review.
- Models may abstain when evidence is insufficient.

The existing 99.84% classifier is archived as a legacy experiment. It cannot be advertised as a production polyphony model unless it passes the new gold benchmark and is actually wired into the runtime.

## 8. Matching design

### Physical fragment matching

Features may include complementary fracture geometry, scale, thickness, curvature, surface normals, 3D alignment, tablet fabric, ductus, and material compatibility. Candidate generation and final ranking are separate. Scores are trained or calibrated on accepted joins and difficult non-joins.

### Textual matching

Features may include line-boundary continuation, lexical and morphological continuity, duplicated passages, sign order, orthography, scribal hand, genre, period, and archive. Generic multilingual sentence embeddings are baselines, not proof of semantic continuity.

### Material provenance

Material inference is enabled only for records with documented measurements. pXRF, SEM-EDX, petrography, INAA, or other methods retain their instrument-specific uncertainty and reference populations. Textual/geographical metadata can inform a joint hypothesis but cannot masquerade as a chemical measurement.

### Combined ranking

The UI shows component scores before any combined score. Combination weights are learned or calibrated from a labeled validation set. A missing modality is represented as missing, not as a neutral invented value.

## 9. Myth knowledge graph and historical inference

The current one-label-per-text design becomes a passage-level, versioned knowledge graph. It represents:

- compositions, tablets, witnesses, passages, and proposed redaction layers;
- characters, divine roles, places, objects, events, formulas, and motifs;
- explicit parallels and transformations between passages;
- date intervals and geographical distributions;
- who or what asserted each relationship.

Historical inference compares competing mechanisms:

- vertical inheritance or common ancestry;
- horizontal diffusion through contact, trade, conquest, schools, or literary transmission;
- contamination/composite traditions;
- independent convergence;
- preservation and sampling bias.

A tree is shown only after a tree-likeness test and with computed support. Otherwise the primary representation is a network. Dates are intervals or probability distributions, not single inferred years. Outputs are worded as hypotheses with counter-evidence and sensitivity analysis.

## 10. Expert review workflow

1. A model or contributor proposes an annotation or match.
2. The proposal is immutable and remains `pending`.
3. A reviewer sees the source passage/media, alternatives, and feature evidence.
4. The reviewer accepts, rejects, or creates a revised assertion.
5. Accepted annotations enter a versioned gold set only after governance checks.
6. Training runs refer to an immutable gold-set version.

User corrections must never alter active runtime rules before review.

## 11. Research interface

The Streamlit interface is retained initially but reorganized around research tasks:

- artifact dossier with source conflicts and material evidence;
- reading workspace with sign candidates, transliteration, morphology, and aligned translations;
- match review with separate physical, textual, and material evidence;
- motif/passages workspace with annotation history;
- hypothesis lab with cohort definition, competing models, diagnostics, and reproducible export;
- data and model registry with cards, licenses, benchmarks, and known limitations.

Badges such as “BERT”, “validated”, or “high confidence” are derived from the experiment/model registry rather than hardcoded presentation text.

## 12. Migration from the current repository

### Preserve

- UI concepts and useful visual components from `app.py`.
- The morphology engine as a rule-based baseline, after tests and normalization fixes.
- Corpus registry concepts after replacement with the canonical source model.
- Contour and Virtual Joiner code as unvalidated baselines.
- Existing databases, model checkpoints, and generated files as checksummed legacy snapshots.

### Replace or retire

- missing `run_me*` orchestration;
- absolute paths and implicit database selection;
- synthetic myths presented as corpus data;
- random bootstrap support and fixed migration confidence;
- placeholder translations and upload matching;
- misleading BERT labels;
- duplicate or broken console entrypoints;
- large training checkpoints and optimizer state in ordinary Git history.

No destructive migration occurs. Legacy data is imported into a staging schema, profiled, and promoted only when its provenance and semantics are known.

## 13. Foundation phases

### Phase 0 — repository safety and reproducibility

- Work only on `codex/evidence-first-foundation` until reviewed.
- Inventory the uncommitted desktop changes without overwriting them.
- Decide which local changes to port deliberately.
- Fix package layout and console entrypoints.
- Introduce typed configuration and remove absolute paths.
- Create deterministic schema migrations.
- Repair pytest configuration and establish CI.
- Make a minimal Docker image start with a fixture database and a real healthcheck.
- Separate Git source from large datasets/checkpoints.
- Correct licensing and product-status documentation.

**Acceptance:** a fresh clone can install, test, start, and execute one end-to-end fixture workflow using documented commands.

### Phase 1 — canonical evidence store and corpus adapters

- Implement the core evidence, assertion, review, and snapshot schema.
- Add CDLI and ORACC adapters with frozen fixtures.
- Generate ingest quality reports and source crosswalks.
- Import a read-only sample of legacy data with explicit `legacy` origin.
- Build artifact and passage APIs used by the UI.

**Acceptance:** every displayed artifact field can be traced to a source snapshot or a versioned assertion.

### Phase 2 — measured language baseline

- Define Akkadian and Sumerian benchmark cards.
- Build leakage-resistant data splits.
- Implement rule/dictionary and retrieval baselines.
- Integrate morphology as one versioned analysis method.
- Evaluate existing checkpoints without privileged labels.
- Add aligned translation hypotheses with abstention and review.

**Acceptance:** benchmark reports are reproducible, stratified, and linked to the exact data/model versions; the UI never labels a rule engine as BERT.

Later phases add calibrated fragment matching, material provenance, motif annotation, and historical inference in that order.

## 14. Verification gates

Every implementation change must pass:

- unit and integration tests;
- a clean package build and installed-entrypoint test;
- lint/type checks at an agreed baseline with no new debt;
- migration upgrade/downgrade checks on disposable databases;
- fixture ingest determinism;
- license and source-manifest validation;
- artifact checksum verification;
- an end-to-end research workflow test;
- documentation checks for commands and links.

Scientific components additionally require frozen gold data, a baseline comparison, calibration/error analysis, and an expert-readable model or method card.

## 15. Success criteria

The foundation is successful when:

1. GitHub and the selected development branch are reproducible from a clean machine.
2. No runtime result depends on a hardcoded local path or silently selected database.
3. Raw evidence and derived claims cannot be confused in schema, API, UI, or export.
4. All visible quality claims come from stored benchmark results.
5. The first Akkadian and Sumerian workflows expose alternatives and uncertainty.
6. Model feedback requires review before entering active rules or gold data.
7. Physical, textual, and material match evidence remains independently inspectable.
8. Historical analyses compare tree and network explanations and expose sensitivity to dating, geography, and sampling.

## 16. Design decisions requiring confirmation

The implementation plan will assume the following unless revised:

- Route B remains the governing strategy.
- Akkadian and Sumerian are the first supported language tracks.
- The initial application remains a modular Python monolith with Streamlit, while domain logic moves into an installable `src/` package.
- PostgreSQL is the intended shared research database; SQLite remains the local/test option.
- GitHub stores code and small fixtures, not multi-gigabyte optimizer/checkpoint duplication.
- Material provenance stays disabled for artifacts without laboratory or documented material measurements.
