# Local translation comparison — 12 September 2026

The installed local model generated an output for each of 20 sourced comparisons: 15 Sumerian passages across 11 tablets, and five Akkadian passages across two inscriptions. This selected sample checks the working inference route and makes errors inspectable. It does **not** establish translation accuracy or reproduce the model author's benchmark.

| Language | Examples | Generated / refused | BLEU | chrF |
|---|---:|---:|---:|---:|
| Sumerian | 15 | 15 / 0 | 69.76 | 83.09 |
| Akkadian | 5 | 5 / 0 | 3.43 | 27.57 |

Metrics compare text similarity to one published reference per example; scores are on a 0–100 scale, not percentages of correct translations. SacreBLEU 2.6.0 was used. BLEU signature: `nrefs:1|case:mixed|eff:no|tok:13a|smooth:exp|version:2.6.0`; chrF signature: `nrefs:1|case:mixed|eff:yes|nc:6|nw:0|space:no|version:2.6.0`. Refusals, if present, are included as empty predictions. CPU inference used PyTorch 2.13.0, Transformers 5.15.0, four beams, no sampling and a 192-token output limit.

## What the outputs reveal

The complete dedication P432172 closely follows its published English reference, with a spelling difference in a proper name. Other passages reveal consequential errors: P470063 changes a reference count of 1232 to 132; P127343 changes the numeral in a festival designation from 7 to 1. Akkadian output often consists of disconnected dictionary meanings, omissions and additions. These results justify treating the model as an editorial aid that always requires review.

All 15 Sumerian examples contain source segments also found in the author's [public training file](https://github.com/leedrake5/cuneiform/blob/5fe5c0771aa9fbcd86bb02c1d84afb1838030c8e/data/s_train.tr): 58 of 59 constituent segment occurrences match, and 31 also match the corresponding English reference after edge-whitespace trimming. Joining seen lines does not create unseen data. The exact checkpoint training manifest was not verified; Akkadian training overlap was not checked. Four Akkadian examples come from one inscription. Neither language sample is representative, and the Sumerian score cannot be used as held-out validation.

## Sources and reuse

- Sumerian: [MTAAC/CDLI Ur III ATF corpus](https://github.com/cdli-gh/mtaac_cdli_ur3_corpus/tree/8de9ca283f7bf9308928c4dd707b3a9b720e7491/ur3_corpus_data/atf), with the repository's [CC0-1.0 dedication](https://github.com/cdli-gh/mtaac_cdli_ur3_corpus/blob/8de9ca283f7bf9308928c4dd707b3a9b720e7491/README.md). Selected documents: P432172, P432274, P432114, P416407, P470063, P470070, P392629, P127343, P384816, P100023 and P101918. Translators include Daniel A. Foxvog, Xiaoli Ouyang, William R. Brookman, Adam E. Miglio, Sara Brumfield, Lance Allred, Markus Hilgert, Eleanor Robson, Kathleen Clark and Robert K. Englund; per-example credits are in the delivered methodology.
- Akkadian: [Akkademia test input](https://github.com/gaigutherz/Akkademia/blob/4684b30d95cfc02c22ec2b4d006ba65d2bbd6996/NMT_input/test.tr) and [English references](https://github.com/gaigutherz/Akkademia/blob/4684b30d95cfc02c22ec2b4d006ba65d2bbd6996/NMT_input/test.en), rows 110, 111, 113, 115 and 123. Scholarly editions [Q003517](https://oracc.museum.upenn.edu/rinap/rinap3/Q003517/html) and [Q003574](https://oracc.museum.upenn.edu/rinap/rinap3/Q003574/html) credit A. Kirk Grayson, Jamie Novotny and the RINAP Project, under CC BY-SA 3.0. Preserve attribution and share-alike conditions for reused or adapted edition text. The upstream software's MIT license does not replace the text license.
- Model: [B. Lee Drake, cuneiformBase-400m](https://huggingface.co/Thalesian/cuneiformBase-400m/tree/5cd996298b654eb60ea3cc0ed30e62ccefb94aef), pinned revision `5cd996298b654eb60ea3cc0ed30e62ccefb94aef`, Apache-2.0 model-card declaration. No model weights or reference datasets are included in the wheel.

## Reproduction

The delivered JSON set records `dataset` provenance and `examples` with `id`, `source_language`, `text`, `reference`, `source_url` and `license`. The accompanying provenance audit preserves source file lines, checksums, translator credits and overlap matches. Source references were not generated or corrected.

```bash
python -m pip install -e '.[translation,evaluation]'
isc-helwigii download-model ./models/cuneiformBase-400m
python scripts/evaluate_translation.py translation-smoke-pairs.json --model-dir ./models/cuneiformBase-400m --output new-results.json
```

The new output contains every prediction, input, model setting, refusal reason and metric signature. Use a new filename for each run. Keep the supplied license and methodology files with the reference set.
