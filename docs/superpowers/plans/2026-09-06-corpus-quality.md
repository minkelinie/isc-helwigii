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

## Delivery checklist (controller)

- [ ] Task review and any corrections; validate the real 37,139-record project independently with SQL and report timings without a hardware guarantee.
- [ ] Wheel and full test verification on reviewed code; browser smoke check; publish updated branch and inspect CI.
- [ ] Save a concise Dutch result, corpus summary and open scientific gates to outputs. Existing source data and earlier outputs remain intact.
