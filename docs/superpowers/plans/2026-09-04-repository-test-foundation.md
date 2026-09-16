# Repository and Test Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ISC Helwigii reproducible from a fresh clone with a valid Python package, deterministic configuration, a tested database-health path, continuous integration, and an honest runnable Docker foundation.

**Architecture:** Replace broken top-level console entrypoints with a small `src/isc_helwigii` package while leaving legacy research scripts available for deliberate later migration. Introduce typed environment-driven settings and a read-only database inspector, then test the installed wheel and Docker-facing health command as external contracts.

**Tech Stack:** Python 3.11/3.12, setuptools, pytest, SQLite, argparse, Streamlit, Docker Compose, GitHub Actions, Ruff.

**Spec:** `docs/plans/2026-09-04-evidence-first-foundation-design.md`

## Global Constraints

- Work only on `codex/evidence-first-foundation`; do not modify the dirty desktop checkout.
- Akkadian and Sumerian are the first measured language tracks, but this plan does not train language models.
- Raw evidence is immutable and derived claims are versioned; this plan creates no scientific claims.
- PostgreSQL is the intended shared research store; SQLite remains the local/test option.
- Git stores code, manifests, and small fixtures, not new model checkpoints, optimizer state, or corpus databases.
- Existing large databases and models remain untouched legacy snapshots.
- Use test-driven development for behavior changes and one focused commit per task.
- Run all shell commands through `rtk`.
- Phase 1 corpus/schema work and Phase 2 language benchmarking receive separate implementation plans after this foundation passes.

---

## File map

### New package

- `src/isc_helwigii/__init__.py` — distribution version export.
- `src/isc_helwigii/cli.py` — stable installed command surface.
- `src/isc_helwigii/config.py` — environment-driven runtime paths.
- `src/isc_helwigii/database.py` — read-only SQLite health inspection.

### New tests and checks

- `tests/test_cli.py` — CLI version, config, and health behavior.
- `tests/test_config.py` — path precedence and directory creation.
- `tests/test_database.py` — missing, invalid, empty, and populated database reports.
- `tests/test_distribution.py` — package metadata and banned console-target regression tests.
- `scripts/check_wheel.py` — installed-wheel smoke check from outside the repository.
- `.github/workflows/ci.yml` — lint, tests, wheel build, and installed-wheel smoke job.

### Existing files changed

- `pyproject.toml` — valid pytest configuration, `src` package discovery, one working console script, dependency and tool scopes, correct repository URLs.
- `requirements.txt` — remains aligned with runtime dependencies.
- `Dockerfile` — installs the wheel and uses the Python health command instead of missing `curl`.
- `docker-compose.yml` — explicit data/database environment and non-destructive volume behavior.
- `.gitignore` — excludes runtime data, build products, and local environment files.
- `.gitattributes` — limits LFS to intentional large artifact patterns.
- `README.md` — evidence-first alpha status and verified setup commands.
- `docs/index.md` and `mkdocs.yml` — remove missing-module instructions and stale repository links.
- `docs/repository-policy.md` — code/data/model storage and licensing boundary.

---

### Task 1: Restore the canonical test command

**Files:**
- Modify: `pyproject.toml:128-145`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: the existing three committed tests.
- Produces: `rtk python3 -m pytest -q` as the canonical passing local test command.

- [x] **Step 1: Run the canonical test command and capture the expected failure**

Run: `rtk python3 -m pytest -q`

Expected: exit 4 while resolving `numpy.VisibleDeprecationWarning`.

- [x] **Step 2: Remove only the invalid warning filter**

Change the pytest warning configuration to:

```toml
filterwarnings = [
    "ignore::DeprecationWarning"
]
```

Do not pin NumPy merely to keep a removed warning class alive.

- [x] **Step 3: Run the canonical tests**

Run: `rtk python3 -m pytest -q`

Expected: 3 passed, exit 0.

- [x] **Step 4: Commit**

```bash
rtk git add pyproject.toml
rtk git commit -m "test: restore canonical pytest command"
```

---

### Task 2: Establish one valid installable package and CLI

**Files:**
- Create: `src/isc_helwigii/__init__.py`
- Create: `src/isc_helwigii/cli.py`
- Create: `tests/test_cli.py`
- Create: `tests/test_distribution.py`
- Modify: `pyproject.toml:45-87,128-151`

**Interfaces:**
- Consumes: distribution metadata from `importlib.metadata`.
- Produces: `isc_helwigii.__version__: str`, `isc_helwigii.cli.main(argv: Sequence[str] | None = None) -> int`, and installed command `isc-helwigii`.

- [x] **Step 1: Write failing package and CLI tests**

```python
from importlib.metadata import version

import pytest

import isc_helwigii
from isc_helwigii.cli import main


def test_package_version_matches_distribution() -> None:
    assert isc_helwigii.__version__ == version("isc-helwigii")


def test_cli_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert version("isc-helwigii") in capsys.readouterr().out
```

Add this installed-metadata contract test to `tests/test_distribution.py`:

```python
from importlib.metadata import distribution

from isc_helwigii.cli import main


def test_console_entrypoint_loads_packaged_main() -> None:
    entries = [
        entry
        for entry in distribution("isc-helwigii").entry_points
        if entry.group == "console_scripts"
    ]
    assert [(entry.name, entry.value) for entry in entries] == [
        ("isc-helwigii", "isc_helwigii.cli:main")
    ]
    assert entries[0].load() is main
```

- [x] **Step 2: Run the tests to verify import failure**

Run: `rtk python3 -m pytest tests/test_cli.py tests/test_distribution.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'isc_helwigii'`.

- [x] **Step 3: Add minimal package implementation**

`src/isc_helwigii/__init__.py`:

```python
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("isc-helwigii")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]
```

`src/isc_helwigii/cli.py`:

```python
from __future__ import annotations

import argparse
from collections.abc import Sequence

from isc_helwigii import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="isc-helwigii")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
```

Change packaging to:

```toml
[project.scripts]
isc-helwigii = "isc_helwigii.cli:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["isc_helwigii*"]
```

Change coverage to:

```toml
[tool.coverage.run]
source = ["src/isc_helwigii"]
```

Correct all `[project.urls]` values from `SignumCore` to `minkelinie` and point documentation to the repository `docs/` directory until Pages is actually deployed.

- [x] **Step 4: Install the branch editable without fetching dependencies**

Run: `rtk proxy .venv/bin/python -m pip install --no-deps --no-build-isolation -e .`

Expected: `isc-helwigii==2.0.0` installs successfully.

- [x] **Step 5: Run focused and complete tests**

Run: `rtk python3 -m pytest tests/test_cli.py tests/test_distribution.py -q`

Expected: all focused tests pass.

Run: `rtk python3 -m pytest -q`

Expected: all tests pass.

- [x] **Step 6: Commit**

```bash
rtk git add pyproject.toml src/isc_helwigii tests/test_cli.py tests/test_distribution.py
rtk git commit -m "build: add installable isc helwigii package"
```

---

### Task 3: Add deterministic runtime settings

**Files:**
- Create: `src/isc_helwigii/config.py`
- Create: `tests/test_config.py`
- Modify: `src/isc_helwigii/cli.py`

**Interfaces:**
- Produces: `Settings.from_env(environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Settings`.
- Produces: `Settings.ensure_directories() -> None`.
- Produces CLI subcommand: `isc-helwigii config --json`.

- [x] **Step 1: Write failing configuration tests**

```python
import json
from pathlib import Path

import pytest

from isc_helwigii.cli import main
from isc_helwigii.config import Settings


def test_explicit_database_path_wins(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.db"
    settings = Settings.from_env(
        {
            "ISC_HELWIGII_DATA_DIR": str(tmp_path / "data"),
            "ISC_HELWIGII_DB_PATH": str(explicit),
        }
    )
    assert settings.database_path == explicit


def test_data_directory_supplies_default_paths(tmp_path: Path) -> None:
    settings = Settings.from_env({"ISC_HELWIGII_DATA_DIR": str(tmp_path)})
    assert settings.database_path == tmp_path / "cuneiform_master.db"
    assert settings.export_dir == tmp_path / "export"
    assert settings.image_dir == tmp_path / "images"


def test_ensure_directories_does_not_create_database(tmp_path: Path) -> None:
    settings = Settings.from_env({"ISC_HELWIGII_DATA_DIR": str(tmp_path / "data")})
    settings.ensure_directories()
    assert settings.data_dir.is_dir()
    assert settings.export_dir.is_dir()
    assert settings.image_dir.is_dir()
    assert not settings.database_path.exists()


def test_config_command_emits_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ISC_HELWIGII_DATA_DIR", str(tmp_path))
    assert main(["config", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["database_path"] == str(tmp_path / "cuneiform_master.db")
```

- [x] **Step 2: Run tests to verify missing module and command failures**

Run: `rtk python3 -m pytest tests/test_config.py -q`

Expected: collection fails for missing `isc_helwigii.config`.

- [x] **Step 3: Implement typed settings**

`src/isc_helwigii/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    database_path: Path
    export_dir: Path
    image_dir: Path

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> "Settings":
        values = os.environ if environ is None else environ
        base = Path(values.get("ISC_HELWIGII_DATA_DIR", (cwd or Path.cwd()) / "data"))
        return cls(
            data_dir=base,
            database_path=Path(values.get("ISC_HELWIGII_DB_PATH", base / "cuneiform_master.db")),
            export_dir=Path(values.get("ISC_HELWIGII_EXPORT_DIR", base / "export")),
            image_dir=Path(values.get("ISC_HELWIGII_IMAGE_DIR", base / "images")),
        )

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.export_dir, self.image_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}
```

Extend the CLI with a `config` subparser. For `config --json`, print `json.dumps(Settings.from_env().to_dict(), indent=2, sort_keys=True)`.

- [x] **Step 4: Run focused and complete tests**

Run: `rtk python3 -m pytest tests/test_config.py -q`

Expected: 4 passed.

Run: `rtk python3 -m pytest -q`

Expected: all tests pass.

- [x] **Step 5: Commit**

```bash
rtk git add src/isc_helwigii/config.py src/isc_helwigii/cli.py tests/test_config.py
rtk git commit -m "feat: add deterministic runtime settings"
```

---

### Task 4: Replace legacy pipeline health with a read-only database contract

**Files:**
- Create: `src/isc_helwigii/database.py`
- Create: `tests/test_database.py`
- Modify: `src/isc_helwigii/cli.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Settings.database_path`.
- Produces: `DatabaseReport(status: str, path: Path, schema: str, tables: tuple[str, ...], counts: dict[str, int], error: str | None)`.
- Produces: `inspect_database(path: Path) -> DatabaseReport`.
- Produces CLI subcommand: `isc-helwigii health [--database PATH] [--json]`.

- [x] **Step 1: Write failing inspector tests**

```python
import sqlite3
from pathlib import Path

from isc_helwigii.database import inspect_database


def test_missing_database_is_unavailable(tmp_path: Path) -> None:
    report = inspect_database(tmp_path / "missing.db")
    assert report.status == "unavailable"
    assert report.error == "database does not exist"


def test_empty_database_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    report = inspect_database(path)
    assert report.status == "degraded"
    assert report.schema == "unknown"


def test_legacy_database_counts_known_tables(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tablets (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE myth_texts (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO tablets VALUES ('P1')")
    report = inspect_database(path)
    assert report.status == "healthy"
    assert report.schema == "legacy-v2"
    assert report.counts == {"myth_texts": 0, "tablets": 1}


def test_non_sqlite_file_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "invalid.db"
    path.write_text("not sqlite", encoding="utf-8")
    report = inspect_database(path)
    assert report.status == "unavailable"
    assert report.error is not None
```

- [x] **Step 2: Run focused tests to verify failure**

Run: `rtk python3 -m pytest tests/test_database.py -q`

Expected: collection fails for missing `isc_helwigii.database`.

- [x] **Step 3: Implement the inspector**

Use a frozen dataclass with `to_dict()`. Open existing files with SQLite URI `file:{path}?mode=ro` and `uri=True`, enumerate non-internal tables from `sqlite_master`, and count only these known tables when present:

```python
KNOWN_TABLES = (
    "artifacts",
    "source_snapshots",
    "tablets",
    "myth_texts",
    "spijkerschrift",
)
```

Schema classification is deterministic:

```python
if {"artifacts", "source_snapshots"}.issubset(tables):
    schema = "evidence-v1"
elif "tablets" in tables:
    schema = "legacy-v2"
elif "spijkerschrift" in tables:
    schema = "legacy-v1"
else:
    schema = "unknown"
```

Return `healthy` for a recognized schema, `degraded` for an open database with an unknown schema, and `unavailable` for missing/invalid files. Never create or mutate the inspected database.

- [x] **Step 4: Add the health CLI**

Resolve `--database` before `Settings.database_path`, print the complete report as JSON for `--json`, and return exit codes:

- `0` for `healthy`;
- `1` for `degraded`;
- `2` for `unavailable`.

- [x] **Step 5: Retire the misleading pipeline tests**

Replace tests of `OxStealthPipeline.health_check()` with tests of `inspect_database()`. Keep `ox_stealth/pipeline.py` as legacy code during this task, but stop counting it in coverage or importing it from canonical tests.

- [x] **Step 6: Run focused and complete tests**

Run: `rtk python3 -m pytest tests/test_database.py tests/test_cli.py -q`

Expected: all focused tests pass.

Run: `rtk python3 -m pytest -q`

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
rtk git add src/isc_helwigii/database.py src/isc_helwigii/cli.py tests/test_database.py tests/test_pipeline.py
rtk git commit -m "feat: add read-only database health contract"
```

---

### Task 5: Prove the built wheel works outside the repository

**Files:**
- Create: `scripts/check_wheel.py`

**Interfaces:**
- Consumes: a wheel path as `sys.argv[1]` and Python executable as `sys.executable`.
- Produces: exit 0 only when the isolated installed package imports and both `--version` and `config --json` run.

- [x] **Step 1: Create the wheel smoke script**

Create `scripts/check_wheel.py` with ZIP member validation, isolated installation, import, version, and JSON configuration checks.

- [x] **Step 2: Build the current wheel and verify the module CLI contract fails**

Run: `rtk proxy .venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .`

Run: `rtk proxy .venv/bin/python scripts/check_wheel.py dist/isc_helwigii-2.0.0-py3-none-any.whl`

Expected: non-zero because `python -m isc_helwigii.cli --version` produces no version before the module footer exists.

- [x] **Step 3: Remove broad package data**

Delete `[tool.setuptools.package-data]`. Small future fixtures belong in an explicitly named package path and will be added with a narrow rule.

- [x] **Step 4: Add the module execution contract**

`scripts/check_wheel.py` creates a temporary directory and virtual environment, installs the supplied wheel with `pip --no-deps`, and runs:

```python
subprocess.run([venv_python, "-c", "import isc_helwigii"], check=True)
subprocess.run([venv_python, "-m", "isc_helwigii.cli", "--version"], check=True)
subprocess.run([venv_python, "-m", "isc_helwigii.cli", "config", "--json"], check=True)
```

Before installing, the script opens the wheel as a ZIP archive and fails if any member ends in `.db`, begins with `data/` or `models/`, or is a top-level Python module. It also requires `isc_helwigii/__init__.py` and the distribution entry-point metadata. These assertions exercise the built artifact rather than grepping project configuration.

Add this footer to `cli.py` so module execution is a valid installed contract:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 5: Build and smoke-test the wheel**

Run: `rtk python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .`

Expected: one `isc_helwigii-2.0.0-py3-none-any.whl` containing only the new package and distribution metadata.

Run: `rtk python3 scripts/check_wheel.py dist/isc_helwigii-2.0.0-py3-none-any.whl`

Expected: exit 0 from a temporary isolated environment.

- [x] **Step 6: Commit**

```bash
rtk git add pyproject.toml src/isc_helwigii/cli.py scripts/check_wheel.py
rtk git commit -m "test: verify installed wheel contract"
```

---

### Task 6: Add continuous integration gates

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: canonical pytest and wheel commands from Tasks 1 and 5.
- Produces: a Python 3.11/3.12 CI matrix plus a separate packaging job.

- [x] **Step 1: Add the workflow configuration**

The test job must checkout with LFS disabled, install `.[dev]`, run `ruff check src tests scripts`, and run `python -m pytest`. The package job must build with `pip wheel --no-deps --no-build-isolation`, identify the wheel, and run `scripts/check_wheel.py`.

Use permissions:

```yaml
permissions:
  contents: read
```

Do not download Git LFS datasets or models in CI.

- [x] **Step 2: Narrow the initial Ruff gate**

Keep Ruff focused on `src`, `tests`, and `scripts`; do not auto-fix or reformat all legacy research scripts in this foundation task.

- [x] **Step 3: Run local equivalents**

Run: `rtk ruff check src tests scripts`

Expected: exit 0.

Run: `rtk python3 -m pytest -q`

Expected: all tests pass.

- [x] **Step 4: Commit**

```bash
rtk git add .github/workflows/ci.yml pyproject.toml
rtk git commit -m "ci: add test and packaging gates"
```

---

### Task 7: Make the container contract explicit and testable

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `isc-helwigii health --database PATH --json` and settings environment variables.
- Produces: a runtime image that contains installed code but no repository datasets/models and reports missing data honestly.

- [x] **Step 1: Build the package in the Docker builder stage**

Install runtime dependencies, build the wheel, and install the wheel into `/install`. Copy `app.py` separately because Streamlit remains a legacy top-level UI during Phase 0. Do not copy data or model directories because `.dockerignore` excludes them.

- [x] **Step 2: Replace healthchecks**

Dockerfile health command:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD isc-helwigii health --json || exit 1
```

Compose environment:

```yaml
environment:
  ISC_HELWIGII_DATA_DIR: /data
  ISC_HELWIGII_DB_PATH: /data/cuneiform_master.db
```

The container is unhealthy until a recognized database is mounted or initialized. It must not silently fall back to a desktop path.

- [x] **Step 3: Validate the effective Compose configuration**

Run: `rtk docker compose config --quiet`

Expected: exit 0.

- [x] **Step 4: Build and execute the container contract if Docker is available**

Run: `rtk docker build --target runtime -t isc-helwigii:foundation .`

Expected: image builds without downloading LFS objects into the context.

Run: `rtk docker run --rm isc-helwigii:foundation isc-helwigii --version`

Expected: prints version `2.0.0` and exits 0.

Run: `rtk docker run --rm isc-helwigii:foundation isc-helwigii health --json`

Expected: exits 2 and reports `database does not exist`; the image does not invent or bundle research data.

Execution record (2026-09-04): `docker compose config --quiet` passed. Image build and runtime commands could not run because the configured Colima Docker daemon was not running; retain them as final external verification gates.

- [x] **Step 5: Commit**

```bash
rtk git add Dockerfile docker-compose.yml .dockerignore
rtk git commit -m "build: define honest container health contract"
```

---

### Task 8: Protect repository boundaries and correct user-facing setup

**Files:**
- Modify: `.gitignore`
- Modify: `.gitattributes`
- Create: `docs/repository-policy.md`
- Modify: `README.md`
- Modify: `docs/index.md`
- Modify: `mkdocs.yml`
- Create: `scripts/check_docs.py`

**Interfaces:**
- Produces: documented source/data/model boundaries and verified commands.
- Produces: no false CI, BERT, accuracy, or production-readiness claims.

- [x] **Step 1: Create an executable documentation contract**

```python
from __future__ import annotations

from pathlib import Path

import yaml

def nav_paths(items: list[object]) -> list[str]:
    paths: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for value in item.values():
                if isinstance(value, str):
                    paths.append(value)
                elif isinstance(value, list):
                    paths.extend(nav_paths(value))
    return paths


def main() -> int:
    config = yaml.safe_load(Path("mkdocs.yml").read_text(encoding="utf-8"))
    missing = [path for path in nav_paths(config["nav"]) if not (Path("docs") / path).is_file()]
    if missing:
        raise SystemExit("missing MkDocs pages: " + ", ".join(sorted(missing)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 2: Run and verify the current navigation failure**

Run: `rtk python3 scripts/check_docs.py`

Expected: non-zero with the nine missing MkDocs pages.

- [x] **Step 3: Rewrite setup documentation**

README and docs must label the branch as an evidence-first foundation, distinguish current working functionality from planned research capability, and document only commands verified by this plan:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
isc-helwigii --version
isc-helwigii config --json
isc-helwigii health --database /path/to/database.db --json
```

Do not claim that the legacy BERT checkpoint is active or scientifically validated.

- [x] **Step 4: Define repository policy**

State that source code, migrations, small synthetic fixtures, manifests, checksums, cards, and documentation belong in Git. Corpus dumps, `.db` research stores, checkpoints, optimizer state, exports, and user uploads remain external. Preserve current license declarations without silently relicensing code, data, or models; block a public release until the owner chooses an explicit per-artifact license boundary.

- [x] **Step 5: Narrow LFS intent**

Remove `*.py` and broad JSON rules from `.gitattributes`. Keep existing tracked LFS objects untouched during this task; document a later history-cleanup decision rather than rewriting history.

- [x] **Step 6: Run documentation and full tests**

Run: `rtk python3 scripts/check_docs.py`

Expected: exit 0.

Run: `rtk python3 -m pytest -q`

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
rtk git add .gitignore .gitattributes README.md docs/index.md docs/repository-policy.md mkdocs.yml scripts/check_docs.py
rtk git commit -m "docs: define evidence-first repository boundaries"
```

---

### Task 9: Final foundation verification

**Files:**
- Modify only if a verification failure exposes a task-scoped defect.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: a verification record suitable for branch review.

**Verification record (2026-09-04):** the branch was clean before this record was added; Ruff and all 13 tests passed with 92% coverage; the wheel contract passed on the active Python 3.14 environment and clean Python 3.11/3.12 virtual environments; Compose configuration parsed successfully. The Docker image build could not reach the inactive local Colima daemon, so the container runtime remains the only external verification gap. No push or pull request was performed.

- [x] **Step 1: Verify repository state**

Run: `rtk git status --short --branch`

Expected: clean `codex/evidence-first-foundation` branch.

- [x] **Step 2: Run quality gates**

Run: `rtk ruff check src tests scripts`

Expected: exit 0.

Run: `rtk python3 -m pytest -q`

Expected: all tests pass.

- [x] **Step 3: Verify distribution**

Run: `rtk python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .`

Expected: wheel builds.

Run: `rtk python3 scripts/check_wheel.py dist/isc_helwigii-2.0.0-py3-none-any.whl`

Expected: exit 0.

- [x] **Step 4: Verify container configuration**

Run: `rtk docker compose config --quiet`

Expected: exit 0.

Run: `rtk docker build --target runtime -t isc-helwigii:foundation .`

Expected: exit 0 when Docker is available; otherwise record Docker as the only unverified external runtime.

- [x] **Step 5: Review branch diff**

Run: `rtk git diff --check main...HEAD`

Expected: no whitespace errors.

Run: `rtk git log --oneline main..HEAD`

Expected: design, plan, and focused implementation commits are visible.

- [x] **Step 6: Do not push automatically**

Present the verified branch state, test counts, remaining risks, and the proposed GitHub integration action to the owner. Push or open a pull request only after that review.
