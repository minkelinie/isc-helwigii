# Current software status — 13 September 2026

The installable application is `src/isc_helwigii` on `codex/local-research-workbench`. Legacy root scripts and model files are historical experiments, not connected product features. This remains a local research alpha.

| Workflow | Implemented | Validation boundary |
|---|---|---|
| Sources and editions | Immutable imports, media, source checksums, portable project backups | Recorded rights and legacy language/genre fields require source/editorial verification |
| Schema integrity | Shared canonical table/trigger contract at open, health and restore; health quick/FK checks | Software tests detect weakened PK, NOT NULL, FK, UNIQUE and review CHECK constraints; no automatic migration of externally altered schemas |
| Corpus quality | Complete edition inventory, metadata/duplicate issues, reviewed reference preparation | No expert-approved reference set is supplied |
| Research dossier | Selected passage, all-corpus lexical ranking, token alignment/differences, exact reviewed translation memory, frozen experiment and JSON export | Software tested; no scientific retrieval benchmark or translation model accuracy claim |
| Reading and review | Passage annotations, alternative proposals and append-only accepted/rejected decisions | Researcher attribution is not authentication; editorial acceptance is not automatic historical truth |
| Translation workspace | Exact passage selection, attributed proposals and review, edition/target-specific worksheet, overlap conflicts, uncovered passages, Markdown/JSON export and CLI | Editorial coverage counts non-whitespace Unicode characters; it does not measure translation accuracy or infer missing text |
| Local model translation | Pinned cuneiformBase-400m, verified local safetensors, CPU inference, Sumerian/Akkadian-to-English proposals in UI and CLI, recorded source/model/runtime provenance | Experimental model output; explicit review required. No photograph OCR or Dutch model output. Inputs over 512 tokens, unknown tokens and unfinished output are refused |
| Images, material and myths | Media/region annotation, manual join records, lab comparisons, motif overlap and competing hypotheses | OCR, 3D joins, calibrated provenance, ancestry and prehistoric dating remain research work |

The real local project contains 37,139 source-bound editions. A full-corpus dossier for P100003 took 5.432 seconds with 29.0 MiB peak process RSS on the existing macOS/Python 3.14 environment. Ten lexical candidates were returned; translation memory abstained because no accepted exact Dutch translation was available. This is one performance observation, not a quality benchmark. The run adds an experiment; it does not annotate or accept scientific claims.

Software verification on 9 September: 84 tests passed, 89% package coverage, Ruff and documentation navigation passed. The built wheel passed installation into a fresh environment without dependencies, including init/import/export/restore, corpus dossier preparation and health. The live Streamlit page was exercised against the 37,139-edition project. Independent review findings about concurrent source/review snapshots and unbounded translation candidates were fixed and regression-tested; returned translations now share the corpus transaction and include their accepted review provenance.

## How to inspect a result

Software verification on 10 September: 98 tests passed, 90% package coverage, Ruff and documentation navigation passed. A fresh wheel installation without runtime dependencies exercised proposal creation, explicit review and Markdown worksheet export as well as the prior project lifecycle. A live browser on a separate synthetic project verified the second occurrence of a Unicode passage, pending/accepted/rejected transitions, updated coverage and selected review labels, and a Markdown download. Independent review found no remaining serious actionable issues in the translation core, CLI and UI. The real local project was inspected read-only; test translations were not added to it.

Use **Vertalen** to prepare and review translations of a chosen source edition. Select an unchanged passage and its occurrence, record a translation and reference, then review explicitly. Accepted non-overlapping spans appear in the worksheet; overlapping alternatives remain conflicts and missing spans remain open. Download Markdown for reading and JSON for the captured evidence. The worksheet reads source and review state in one transaction without adding a research run or changing source records.

Use **Onderzoeksdossier** in the app. Keep the full source text or paste an unchanged subpassage, select its occurrence when repeated, and prepare the dossier. Read source and candidate side by side. Shared words and words unique to either text are shown separately. Find source bytes and media in **Tabletten**; recorded experiments remain available in **Experimenten & export** after a restart.

Search ranks full editions in exactly the same registered language, excluding all editions of the query artifact. NFC normalization and casefolding retain index digits and damage brackets. Pure placeholders do not contribute. Scores are lexical overlap, not probabilities. Long texts can bury short parallels; differing language labels are not automatically mapped to the same language. Saved results reflect their captured source/review state and should be rerun after new evidence.

## Local translation delivery

The [cuneiformBase-400m model by B. Lee Drake](https://huggingface.co/Thalesian/cuneiformBase-400m) is downloaded separately, pinned to revision `5cd996298b654eb60ea3cc0ed30e62ccefb94aef`. The public model card declares Apache-2.0. Model weights are not redistributed inside the wheel or Git repository. `download-model` is the explicit network operation; inference uses only verified local files and does not execute remote model code.

Software verification on 12 September: the 137-test suite passed with 89% package coverage; Ruff and documentation checks passed. The actual downloaded model also ran through Streamlit AppTest on the CC0 MTAAC/CDLI source P432172. Selecting line 6 produced “king of Sumer and Akkad,” as an inferred, pending proposal with its exact source range and an experiment. The source stayed unchanged and an ordinary UI rerun created no duplicate. The published reference adds “and” at the start. The live browser then generated a full-document proposal, preserved the source and displayed the model/run identifiers. This is integration evidence, not expert validation. Python 3.14.6, PyTorch 2.13.0 and Transformers 5.15.0 were used on CPU.

`scripts/evaluate_translation.py` compares a sourced JSON reference set with actual local predictions using SacreBLEU BLEU and chrF. It preserves dataset provenance, predictions, refusals, model settings and metric signatures, and reports languages separately. Refused inputs remain in metric denominators as empty predictions. Install the optional `evaluation` dependencies to run it. Small samples with unknown training overlap do not establish general translation quality.

Independent expert review, representative language/genre reference sets and controlled training/test separation remain scientific work. The predominantly Sumerian local corpus cannot be validated by an unrelated Akkadian model score. Image translation additionally needs tested sign/line recognition. No local model output is automatically accepted as a historical claim.

The [20-pair local comparison](translation-smoke-2026-09-12.md) exposed numerical errors and gloss-like Akkadian output. All 15 Sumerian examples have source-segment overlap with a published training file; their higher reference-similarity score is not independent validation. Review also identified damage-only inputs such as `[x x]` and `x-x` reaching inference; these are now refused before any run or proposal is written, with six regression cases. Long source/translation/reference displays wrap, and switching the target to English preserves the selected passage without a session-state warning.

Final local checks on 13 September: 143 tests passed, 89% package coverage, Ruff and documentation checks passed. Model/runtime libraries remain optional; the distribution smoke check imports the translation modules without PyTorch or Transformers installed.

The unresolved legacy code/data/model license declarations are preserved. This change does not relicense sources or constitute a formal public release. Older verification reports describe their dated commits and must not be treated as current feature or scientific performance claims.
