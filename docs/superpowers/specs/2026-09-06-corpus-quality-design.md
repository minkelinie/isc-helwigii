# Corpus quality and reference preparation

Continuation of stage 4 in the approved local research roadmap. The owner explicitly asked to continue the next steps. This phase adds a usable source/quality desk and prepares evidence-linked evaluation sets; it does not train a model or certify a gold corpus.

## Design

Add a read-only, deterministic audit over all source snapshots and editions, using one explicit SQLite read transaction and minimal queries, never one dossier/connection per tablet. Reuse schema v1. Imported records and source bytes are never changed. Sources are displayed with license text, adapter and checksum; license presence is not legal validation. Distribution grain is editions, artifact totals count distinct artifact IDs.

Quality rows carry artifact/edition/source identifiers, metadata values, explicit issue codes and text fingerprints. Count unknown language, empty text, missing period/provenience, legacy/synthetic flags, missing accepted composition family, exact normalized duplicates, multiple editions and cross-source identifier collisions. Missing metadata may be inspected in legacy_metadata with its original field path recorded; it is not promoted to accepted evidence. Exact text normalization is NFC + casefold + whitespace collapse only; damage notation, diacritics and index digits remain. Empty and wholly unreadable text is not a duplicate identity. These are audit flags, never proof of erroneous or fake tablets.

Reference export supports category labels on one requested axis, using only currently accepted, unsuperseded category annotations and one accepted non-placeholder composition_family per artifact. Conflicting accepted labels/families, synthetic records, empty/unreadable text and unknown languages are excluded with reasons. Legacy labels are never used as reference labels. Legacy records may enter only through explicit reviewed category/family annotations, not merely their import status. Each item preserves edition, artifact, source snapshot, text, source-record checksum, label/family annotation IDs and their review history. Requiring recorded language is a technical gate, not language verification. Rights remain unresolved and visible, never inferred from arbitrary license text.

Grouping must keep editions of one artifact, composition families and exact normalized duplicates in a transitive component. Group the full corpus including excluded bridge editions before applying eligibility or language/axis filters, so exclusion cannot break a known linkage. Seeded component assignment is deterministic, input-order independent and includes split counts plus a language distribution per split. It is a proposed split, not permanently frozen across later corpus edits; fingerprint changes reveal edits. Empty exports produce a useful abstention report, not an error or a made-up benchmark.

## Public interface and presentation

- New corpus.py for a consistent snapshot, audit, reference preparation and safe JSON export.
- New ui_corpus.py for a Corpuskwaliteit workspace. Show a source register, totals and issue queue with source/language/issue filters, counts and bounded pages. Explain stale results if snapshot-based UI caching is used; never reuse results across project paths or settings. Export audit and reference JSON without changing the research database. Add composition_family to the existing category axis selector with guidance.
- CLI audit PROJECT [--output NEW_JSON] and reference-set PROJECT --axis AXIS [--seed INT] [--output NEW_JSON]. Refuse overwriting any existing output; validate destination differs from the project before writing.
- Existing generic evaluation remains compatible. The new export can feed its ID-to-label gold mapping. All exported objects are plain JSON, no executable code.

Visual direction: keep the existing Streamlit typography, theme and keyboard controls. Left-aligned source register and actionable tables, no ornamental redesign or external font downloads. Counts distinguish tablets from editions. Issues explain what the researcher should verify; no opaque overall quality score.

## Constraints

- Python 3.11+, no new required runtime dependencies or network calls.
- Preserve schema v1, append-only evidence, original source files and real project data.
- Audit/reference generation is read-only; exports refuse overwrite.
- Do not conflate metadata completeness with scientific correctness, rights clearance or representative sampling.
- No automated translation, ancestry, provenance probability or gold-quality claims.

## Acceptance

Full source counts and independent SQL totals agree on the real corpus. Determinism, no mutation, empty projects, mixed/missing metadata, duplicate normalization, accepted/rejected/superseded/conflicting annotations, cross-edition and transitive excluded-bridge leakage, JSON export refusal and UI interactions have tests. Run full pytest, Ruff, wheel lifecycle and existing documentation check. An independent review checks implementation against this spec. Publish on the existing approved branch/PR only; do not merge main.
