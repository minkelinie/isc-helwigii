# Corpus quality and reference preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add a read-only source/quality desk and evidence-linked reference exports to the existing local app.

**Architecture:** One read transaction creates a minimal in-memory snapshot; pure analysis builds the audit and reference set. CLI and Streamlit share the same functions. No database migration.

**Tech Stack:** Python 3.11+, stdlib SQLite/JSON/hashlib, existing Streamlit, pytest/AppTest and Ruff.

**Spec:** docs/superpowers/specs/2026-09-06-corpus-quality-design.md

## Global Constraints

- Python 3.11+, no new required runtime dependencies or network calls.
- Preserve schema v1, append-only evidence, original source files and real project data.
- Audit/reference generation is read-only; exports refuse overwrite.
- Do not conflate metadata completeness with scientific correctness, rights clearance or representative sampling.
- No automated translation, ancestry, provenance probability or gold-quality claims.

### Task 1: Complete corpus-quality desk and reference preparation

**Files:** Create src/isc_helwigii/corpus.py, src/isc_helwigii/ui_corpus.py, tests/test_corpus.py, tests/test_corpus_ui.py. Modify src/isc_helwigii/cli.py, ui_pages.py, capabilities.py; optionally add a reusable component-grouping helper in evaluation.py without changing existing grouped_split contract. Update README.md and docs/local-research-guide.md.

**Interfaces:** `audit_corpus(store) -> dict`, `prepare_reference_set(store, *, axis="genre", seed=42) -> dict`, `write_json_export(value, destination) -> None` in corpus.py. Return audit method, deterministic fingerprint, counts (artifacts, editions, snapshots), sources, distributions and edition-level rows with issues. Reference returns method, fingerprint, parameters, items, exclusions, assignments, counts, gold and limitations. Implementation may use internal helpers for snapshot loading and union-find; do not expose database blobs or mutate evidence.

- [ ] Write focused failing tests before implementation. Use real ResearchStore temporary projects with native records and explicit review events. The audit fixtures must include same external ID from two sources, multiple editions of one artifact, null/blank/placeholder language, a malformed metadata scalar/object, diacritic normalization and distinct index digits.

```python
def test_audit_is_complete_read_only_and_deterministic(tmp_path):
    store = ResearchStore(tmp_path / 'project.db')
    store.initialize()
    store.import_records(b'a', [dict(external_id='A', language='sux', text='a-na')], source='s', license='private')
    before = store.path.read_bytes()
    first = audit_corpus(store)
    assert first == audit_corpus(store)
    assert first['counts']['editions'] == 1
    assert first['counts']['artifacts'] == 1
    assert store.path.read_bytes() == before
```

- [ ] Run `rtk proxy .venv/bin/python -m pytest tests/test_corpus.py -q --no-cov` and record the expected missing-feature failure.
- [ ] Implement snapshot reading with explicit BEGIN under store.connection(), selecting source metadata without raw BLOB, edition records joined once to artifacts and annotation/review rows in the same transaction. Resolve review status identically to dossier(), including accepted supersession. Fingerprint canonical snapshot input so changed sources, records, annotations or reviews change it; do not include a wall-clock timestamp in deterministic outputs.
- [ ] Implement audit counts/metadata distributions and bounded actionable issue rows. Record metadata field paths for legacy fallback. Counts use every edition; multiple editions are not duplicate artifacts. Document unreadable-text policy and thresholds without claiming content validity.
- [ ] Add reference tests that separately reproduce pending/rejected exclusion, accepted inclusion, superseded and conflicting reviews, no legacy-label promotion, multiple editions held together, transitive same-text/family links through excluded records, deterministic seed/order, empty abstention and malformed parameters.

```python
# After explicitly accepted genre and composition_family annotations:
result = prepare_reference_set(store, axis='genre', seed=42)
assert set(result['gold']) == {item['id'] for item in result['items']}
assert len({result['assignments'][item['id']] for item in result['items']
            if item['artifact_id'] == artifact_id}) == 1
```

- [ ] Implement reference gating and union-find over the full corpus, then emit eligible items and exclusions. Families come only from accepted composition_family categories. Group artifact IDs even when texts differ; exact text duplicates connect across sources/languages conservatively. Treat unknown family as absent, never as an invented singleton-family claim. Keep an accepted evidence snapshot including actor/origin/review IDs and source rights for every item.
- [ ] Test CLI JSON output, new-path export and no-overwrite (including a destination equal to project), then implement shared CLI commands and atomic create-only JSON publication. The CLI must return a nonzero code with a useful message for invalid axis, seed or export path.
- [ ] Write AppTest for navigating Corpuskwaliteit, generating a report, filtering its issues and generating a reference export on a synthetic fixture. Implement the workspace with labeled filters and bounded result pages; make no JSON upload necessary to run these workflows. Add composition_family to category axis choices and explain how to record/review it. Do not certify synthetic fixture output as a real benchmark.
- [ ] Document command examples and accepted-label/family workflow, source-rights caveats, normalization, exclusions and changing-corpus split limitations. Add capabilities without changing scientific maturity claims.
- [ ] Run targeted tests, then once `rtk proxy .venv/bin/python -m pytest -q`, `rtk proxy .venv/bin/python -m ruff check src tests scripts`, `rtk proxy .venv/bin/python scripts/check_docs.py`; inspect diff and record TDD evidence in the task report. Commit only scoped code/tests/docs, never real corpus files. Controller handles push/PR and real-data validation.

### Task 2: Verify all required SQLite v1 constraints

**Files:** Modify src/isc_helwigii/store.py. Create tests/test_schema_contract.py. Optional concise addition to docs/local-research-guide.md after Task 1 completes. Do not alter corpus.py/UI code.

**Interfaces:** Existing ResearchStore.initialize(), validate(con), connection() and bundles.restore_bundle remain unchanged. Add an internal trusted table-DDL definition shared by initialize/validate and a lexical normalizer preserving SQL string literals. The required schema is the current seven CREATE TABLE statements, including review decision CHECK, all NOT NULL fields, primary and foreign keys and the two composite uniqueness constraints. Do not add new requirements such as NOT NULL to TEXT PRIMARY KEY columns that v1 did not declare.

- [ ] Write a regression fixture that derives a new empty test schema from actual v1 sqlite_master SQL, but removes one constraint before executing it; keep all column names and triggers. It must currently pass validate and then fail after the fix. Never use PRAGMA writable_schema or alter the user's DB.

```python
def test_reject_missing_edition_foreign_key(tmp_path):
    store = ResearchStore(tmp_path / 'good.db')
    store.initialize()
    # Build an in-memory clone from sqlite_master SQL, replacing only:
    # 'artifact_id TEXT NOT NULL REFERENCES artifacts(id)'
    # with 'artifact_id TEXT NOT NULL' in the editions table.
    with pytest.raises(ValueError, match='schema'):
        ResearchStore.validate(altered_connection)
```

- [ ] Parameterize distinct mutations for removed FK, removed UNIQUE, removed NOT NULL, changed type/PK and removed or weakened review decision CHECK. Include a mutation of a SQL string literal so case/whitespace normalization cannot accidentally accept changed permitted values.
- [ ] Run `rtk proxy .venv/bin/python -m pytest tests/test_schema_contract.py -q --no-cov`; record RED showing altered schema incorrectly accepted.
- [ ] Move only the current table DDL to a reusable constant; initialize retains transaction/index/trigger setup and schema version. Tokenize full CREATE TABLE SQL, comparing every token against the corresponding trusted statement. Ignore whitespace and keyword/identifier case outside literals; preserve literal characters exactly. Reject unmatched/extra tokens. Do not compare generated autoindex names or impose platform-dependent PRAGMA order.
- [ ] Add passing fixtures for unchanged v1 schema and cosmetic external whitespace/keyword-case changes. Verify current source and restored files still open without writes.
- [ ] Build a tampered backup fixture with weakened schema plus recomputed outer SHA-256; restore must reject it and leave destination absent. Test through the public restore function, not merely the helper.
- [ ] Run focused tests, full suite once, Ruff and docs check. Commit scoped changes. Report RED/GREEN evidence, files changed and compatibility observations to the task report; no push or real corpus mutation.

## Delivery checklist (controller)

- [ ] Task review and any corrections; validate the real 37,139-record project independently with SQL and report timings without a hardware guarantee.
- [ ] Wheel and full test verification on reviewed code; browser smoke check; publish updated branch and inspect CI.
- [ ] Save a concise Dutch result, corpus summary and open scientific gates to outputs. Existing source data and earlier outputs remain intact.
