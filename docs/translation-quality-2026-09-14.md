# Translation quality screening — local work, 14 September 2026

The earlier 20-pair comparison showed two concrete numerical errors: 1232 ewes became 132, and a seventh-day name became “House Day 1.” The local application now attaches reproducible review evidence to new model proposals. Generation itself is unchanged. No model accuracy improvement is claimed.

## Scope

`translation-quality-screen-v1` only interprets strictly descending groups of qualified additive counts, with coefficients 1–9 and sign weights `disz=1`, `u=10`, `gesz2=60`, `gesz'u=600`. Selected Unicode spellings are aliases; offsets always refer to the original unmodified passage. This is an explicitly stated counting-system assumption, not a universal interpretation of cuneiform signs. See [CDLI/MTAAC numeracy](https://cdli-gh.github.io/guides/lists.html#numeracy-and-counting), the annotated `gesz2[sixty]` examples in [CDLI P101904](https://cdli.earth/P101904), and the [ORACC ATF primer](https://oracc.museum.upenn.edu/doc/help/editinginatf/primer/).

Damage, supplied readings, unknown signs or coefficients, fractions and other metrological groups are not evaluated. Line breaks separate groups. Sign indices such as `gu4`, `sila3` and `u4` are not treated as quantities. Numeric components within words, such as `e2-u4-7(disz)`, can be signalled; their interpretation still needs a specialist.

The comparison looks for the same integer value in English digit notation, including thousands separators and digit ordinals. Each target occurrence can satisfy at most one source group. It does not align commodities, units or clauses. It does not understand spelled-out English numbers, metrological conversions or implied quantities. Absence of matching digits is therefore an invitation to inspect the evidence, not a conclusive error label. Presence of a value is labelled **limited**, never passed or approved. Text without supported quantities is **not assessed**.

Words containing `{d}`, `{m}`, `{f}` or `{ki}` are listed as name cues for manual comparison. No guessed normalized names or equivalences are generated. Names without these markers are outside this screening.

## Persistence and presentation

New inference output includes method and implementation hashes, source and translation hashes, format and language, exact relative Unicode spans, numerical observations, unassessed groups, name cues and limitations. The same report is stored in the experiment and annotation. Model proposals remain inferred and pending until an explicit human decision. Neither input nor generated text is rewritten. Warnings remain visible after editorial acceptance, in the interface and both worksheet export formats.

Older proposals are not silently reanalysed or changed. They display that no quality report was recorded. Their original runs remain intact. Reading or exporting a worksheet does not rerun the model.

## Evidence boundary

Final local verification: 179 tests passed (89% package coverage; 96% for the new screening module), Ruff and documentation navigation passed. The final wheel installed and exercised the project lifecycle and translation worksheet without runtime dependencies. Review identified and prompted regression fixes for unreadable gaps, trailing damage brackets, partial source/target numbers and distinguishing negative signs from word hyphens.

Rechecking all 20 saved outputs found 16 supported groups across five examples, eight unassessed groups and 15 name cues. The two known numerical errors were signalled. The same restricted check produced no missing-digit alerts in the corresponding reference translations. This is not a false-positive-rate estimate. A fresh local model run on P470063 and P127343 reproduced both faulty outputs and stored the expected warnings as pending proposals in a separate CC0 test project; source editions stayed unchanged. The browser displayed the P127343 warning and its exact source evidence.

The comparison against the 20 previously generated outputs is a regression observation on known examples. The Sumerian examples overlap a published training source and the sample is small and selected. The new checks are neither a held-out benchmark nor an expert quality rating. The five weak Akkadian outputs contain no supported numeric groups; numerical screening cannot validate their syntax or meaning.

The outstanding scientific priorities remain independent tablet/family-level test sets, specialist review, language/genre-specific model comparison, unit and entity alignment, negation and omission checks, and measured calibration or abstention. This local change is not a public release.
