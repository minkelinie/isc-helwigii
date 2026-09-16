# English number phrases — local work, 15 September 2026

The first screening method only recognized digits in English output. A valid rendering such as “three sheep” therefore raised an unnecessary missing-number warning for `3(disz)`. Method `translation-quality-screen-v2` recognizes complete English cardinal and ordinal phrases up to 999,999, including optional “and” within hundreds/thousands and word hyphens. The source-side counting assumptions are unchanged.

A recognized phrase is stored as its original text and Unicode span. “One thousand two hundred and thirty-two” is a single value, 1232; “one hundred three” never supplies a separate 1 or 3. A target occurrence can satisfy only one source group, whether written as digits or words. Unsupported numeric phrases, including mixed digits/words, negative values, fractions and larger scales, are separately recorded in `quantities.target_unassessed`. Digits inside an unsupported phrase cannot satisfy a source count.

Recognition remains lexical: “one” may be a pronoun, “second” may describe quality, and a matched value can belong to a different commodity or unit. Mixed notations, unsupported spellings, coordination without explicit commodities and implicit quantities can still require manual review. This is a bounded review aid, not semantic translation validation or a universal English number parser.

Potential fractional constructions such as “a third” or an ordinal followed by “of” are left unassessed. This can also flag valid ordinal/date wording. Typographic hyphens, spaced negative signs, plural denominators and mixed Unicode fractions are kept within the inspected expression so that a smaller component cannot silently satisfy a count.

## Compatibility and provenance

New reports use method v2, missing-value status `not_found` and target notation labels `digits`, `cardinal_words` or `ordinal_words`. Consumers of embedded reports should inspect the method version. The annotation and experiment continue to retain the same report, with no automatic review or text rewriting.

The report records `implementation_files` for both `translation_quality.py` and `english_numbers.py`. The combined implementation hash is SHA-256 of UTF-8 lines `filename:sha256` with a trailing newline, ordered by filename. Both component hashes are captured when their modules load. Code-file changes do not relabel already loaded code as a new implementation.

Previously recorded v1 results retain their digit-only meaning and saved limitations. The current renderer supports them without mutating, upgrading or regenerating them. Historical reports and the 14 September package remain separate files.

## Verification boundary

The validation examples for English number handling are controlled software cases, not newly discovered ancient translations. The original 20-pair comparison can be rechecked without loading or changing the model. Its training overlap and language/genre limitations remain unchanged. Scientific validation still requires independent expert review and representative held-out tablets and text families.

Final local verification: 234 tests passed with 90% package coverage (97% for English number recognition). Ruff, documentation checks and isolated wheel installation without runtime dependencies passed. Streamlit tests exercised persisted evidence for both a numerical warning and a correctly recognized word-number proposal, including explicit review.

The previous 14 September wheel was used as a checked baseline for eleven controlled comparisons. Word-number cases improved, unsupported mixed or negative expressions no longer supplied partial digit matches, and known wrong values remained flagged. The twenty saved model outputs retained their two numerical warnings; their supplied references had no missing-value warnings under these restricted checks. Two historical v1 reports rendered identically with old and new code and remained byte-for-byte unchanged. Separate review reproduced six fractional/negative boundary errors; regression fixes and rechecking resolved all six. No model weights, source editions or scientific reviews were changed.
