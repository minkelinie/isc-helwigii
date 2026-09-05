"""Typed, environment-driven paths for ISC Helwigii runtimes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Effective filesystem settings without implicit data creation."""

    data_dir: Path
    database_path: Path
    export_dir: Path
    image_dir: Path

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> Settings:
        """Resolve explicit environment values before deterministic defaults."""
        values = os.environ if environ is None else environ
        base = Path(values.get("ISC_HELWIGII_DATA_DIR", str((cwd or Path.cwd()) / "data")))
        return cls(
            data_dir=base,
            database_path=Path(
                values.get("ISC_HELWIGII_DB_PATH", str(base / "cuneiform_master.db"))
            ),
            export_dir=Path(values.get("ISC_HELWIGII_EXPORT_DIR", str(base / "export"))),
            image_dir=Path(values.get("ISC_HELWIGII_IMAGE_DIR", str(base / "images"))),
        )

    def ensure_directories(self) -> None:
        """Create runtime directories while leaving the database untouched."""
        for directory in (self.data_dir, self.export_dir, self.image_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, str]:
        """Return JSON-ready effective settings."""
        return {key: str(value) for key, value in asdict(self).items()}
