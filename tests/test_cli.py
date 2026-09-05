import json
from importlib.metadata import version
from pathlib import Path

import pytest

import isc_helwigii
from isc_helwigii.cli import main


def test_package_version_matches_distribution() -> None:
    """Catches a package version that drifts from installed metadata."""
    assert isc_helwigii.__version__ == version("isc-helwigii")


def test_cli_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Catches a console command that cannot report its installed version."""
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert version("isc-helwigii") in capsys.readouterr().out


def test_health_command_reports_missing_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Catches a missing database being hidden behind a successful health exit."""
    path = tmp_path / "missing.db"

    assert main(["health", "--database", str(path), "--json"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unavailable"
    assert payload["path"] == str(path)
    assert payload["error"] == "database does not exist"
