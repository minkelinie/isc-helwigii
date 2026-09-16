# Saved translation rechecks — 16 September 2026

Work begun locally on 15 September and included in the 16 September development-branch update. The [previous number-screen update](translation-quality-2026-09-15.md) improved new reports but did not provide a persistent way to apply the newer method to existing proposals. The new `recheck-translation` command and **Opgeslagen voorstel hercontroleren** UI action close that gap.

## Evidence and behavior

- The action reads a saved translation annotation and its immutable source edition. It uses the stored Unicode range and target text, including repeated-passage positions, independently of any open draft.
- Source language and input notation are explicit recorded choices. The UI suggests values from the original quality report, when available; otherwise it uses the known edition language and requires a notation choice. It does not infer transliteration from Unicode content or rewrite source metadata.
- A separate `translation-quality-recheck-v1` experiment stores the annotation ID and payload hash, artifact/edition/snapshot IDs, exact passage and translation, declared and selected languages, notation and offsets. Its output is the current quality-screen report, including method, implementation hashes and text hashes.
- The action performs no model inference or network requests. It creates no annotation or review and does not change editorial coverage. The original report and model run remain historical evidence.
- Each explicit invocation adds a new experiment. Viewing, exporting and ordinary UI reruns add none. Every matching recheck is displayed in append order, with researcher, timestamp and run ID.
- The worksheet reads reviews, annotations and rechecks within its existing single SQLite read transaction. Rechecks affect the worksheet fingerprint. The JSON field `quality_rechecks` is additive; older worksheets remain renderable.
- Reports are attached only when their recorded inputs match the exact proposal and their source/target hashes and language/notation agree. Incomplete or mismatched generic experiment records are excluded from the worksheet but retained in the experiment log. These checks verify linkage and renderability, not a report's scientific truth or authorship.
- Markdown includes the original report and separate recheck sections. JSON and full project bundles preserve the recorded inputs and outputs. No schema migration is needed.

## Validation

The full suite passed: **248 tests, 90% package coverage**, including 14 new core/UI cases. Coverage includes pending, accepted and rejected proposals; exact repeated Unicode passage selection; invalid requests; unrelated/malformed experiments; concurrent snapshot consistency; export/restore; CLI persistence; draft isolation; and no duplicate on ordinary UI rerun.

Ruff, documentation checks and `git diff --check` passed. The wheel passed installation into a fresh environment without runtime dependencies, including the new CLI command, unsupported-target abstention and Markdown/JSON recheck exports. Local wheel SHA-256: `71c421bce8d44a665cfe1c2d7a0f3aefca72c133ae26c13150286906bd4a4145`.

A separate project copy rechecked the previously saved CC0-source model proposals for P127343 and P470063. Both retained their v1 reports and model outputs unchanged. Both still have one numerical warning under v2, as expected: this workflow does not fix the model's wrong output. Both remained pending with unchanged coverage. Original dossiers and model runs were equal before and after; the original project file checksum was unchanged. Bundle export/restore preserved the new history. PyTorch and Transformers were not loaded. Evidence is in the local task's `outputs/hercontrole-integratie-2026-09-15.json` and its two dated worksheet exports.

On 16 September the live browser used another separate project copy, selected P127343's saved 0–88 proposal, and appended one v2 recheck. The UI displayed both methods, retained the numerical warning and showed the proposal as pending.

After downloading the Markdown worksheet, the project still contained exactly one additional run and unchanged original source/proposal/review dossiers. The browser was restored to the main 37,139-tablet project. Browser proof and exports are in the local task's `outputs/hercontrole-browserproef-2026-09-16.json` and `outputs/hercontrole-browserproef-P127343-2026-09-16.*`.

An additional agent code review could not start because of an account usage limit. This round therefore has automated verification and a primary-agent review, without an independent code-review conclusion.

## Scientific boundary and next work

The screening assumptions and limits are unchanged: restricted additive quantity notation, English number phrases, no unit/entity alignment, no meaning validation and no automatic correction or acceptance. Rechecking is provenance-preserving software behavior, not evidence of higher translation accuracy.

The next scientific priority is an independently reviewed reference set, separated from training sources at tablet/edition level and evaluated by language and genre. The current 20-pair exploratory comparison remains unsuitable as an independent accuracy benchmark because all fifteen Sumerian examples overlap a published training source. A review workflow can prepare the evidence and record expert decisions; software alone cannot supply those expert judgments.
