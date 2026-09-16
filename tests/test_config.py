import json
from pathlib import Path

import pytest

from isc_helwigii.cli import main
from isc_helwigii.config import Settings


def test_explicit_database_path_wins(tmp_path: Path) -> None:
    """Catches an explicit database path being replaced by the data default."""
    explicit = tmp_path / "custom.db"

    settings = Settings.from_env(
        {
            "ISC_HELWIGII_DATA_DIR": str(tmp_path / "data"),
            "ISC_HELWIGII_DB_PATH": str(explicit),
        }
    )

    assert settings.database_path == explicit


def test_data_directory_supplies_default_paths(tmp_path: Path) -> None:
    """Catches related runtime paths resolving outside the selected data root."""
    settings = Settings.from_env({"ISC_HELWIGII_DATA_DIR": str(tmp_path)})

    assert settings.database_path == tmp_path / "cuneiform_master.db"
    assert settings.export_dir == tmp_path / "export"
    assert settings.image_dir == tmp_path / "images"


def test_ensure_directories_does_not_create_database(tmp_path: Path) -> None:
    """Catches configuration setup silently creating an empty research database."""
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
    """Catches the installed CLI hiding or misreporting its effective paths."""
    monkeypatch.setenv("ISC_HELWIGII_DATA_DIR", str(tmp_path))

    assert main(["config", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "data_dir": str(tmp_path),
        "database_path": str(tmp_path / "cuneiform_master.db"),
        "export_dir": str(tmp_path / "export"),
        "image_dir": str(tmp_path / "images"),
    }
