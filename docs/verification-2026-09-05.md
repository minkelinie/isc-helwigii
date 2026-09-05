# Local research workbench verification — 2026-09-05

## Software verification

- 54 tests passed on macOS / Python 3.14.6; package coverage 86%.
- Ruff and executable documentation navigation checks passed.
- The built wheel installed in fresh Python 3.11, 3.12 and 3.14 environments without runtime dependencies. Initialization, demonstration import, backup, restore and listing all passed.
- Streamlit interaction tests covered project initialization, demonstration import, all research pages and saving a translation proposal.
- An independent read-only code review identified four defects: replacement bypass, incomplete backup integrity checks, overbroad revision scope and missing-language matching. Regression tests reproduced all four before fixes; the reviewer verified the corrections.
- Docker image `isc-helwigii:local-research` built successfully on Linux arm64 using Python 3.12. Its default command initialized the project as a non-root user. Database health, HTTP health and all eight research pages passed in a temporary container.
- The temporary test container was stopped after verification. The native application remains the normal local launch route.
- GitHub push CI passed its Python 3.11, Python 3.12 and installed-wheel jobs for implementation commit `7040538`. Publication is [pull request #1](https://github.com/minkelinie/isc-helwigii/pull/1), not a merge into main.

## Local corpus verification

The user's existing SQLite corpus was read without modification. A selected query with an upper limit of 50,000 returned all 37,139 tablet rows and created 37,139 evidence editions in a separate research project. The original table contains 13,814,957 transliteration characters. Original generated labels remain legacy metadata; no scientific annotations or results were fabricated.

The complete project was exported and restored to a separate verification file. Counts matched, and archive, raw-source and schema integrity checks passed. On this machine a 200-result first page took approximately 0.57 seconds; a `lugal` search returning 20 rows took approximately 0.16 seconds. These are individual observations, not cross-platform performance guarantees.

## Scientific and operational boundaries

This is a working local alpha, not the final universally capable research system. Present capabilities support human annotation and reproducible exploratory analysis. Automatic OCR, trained Akkadian/Sumerian translation, metric 3D joining, calibrated geographic provenance and validated myth ancestry/prehistoric dating remain unimplemented scientific capabilities.

Reviewers are locally attributed, not authenticated. Windows, GPU workloads, multi-user concurrency and accessibility have not been validated. Complete ORACC CDL/eBL ingestion and source-level review of the legacy corpus remain open. The small software fixtures do not constitute language or archaeology gold benchmarks.

The new publication branch starts directly from GitHub main (`61adc59`). It excludes the eight unpublished local history commits and their multi-gigabyte LFS uploads. The pre-existing desktop checkout and the previous foundation branch are preserved.
