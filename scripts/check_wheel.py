#!/usr/bin/env python3
"""Verify the built distribution from an isolated environment."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


def validate_members(wheel_path: Path) -> None:
    """Reject research data and unpackaged top-level modules in the wheel."""
    with zipfile.ZipFile(wheel_path) as archive:
        members = archive.namelist()

    required_suffixes = (
        "isc_helwigii/__init__.py",
        "isc_helwigii/cli.py",
        ".dist-info/entry_points.txt",
    )
    missing = [
        suffix for suffix in required_suffixes if not any(m.endswith(suffix) for m in members)
    ]
    if missing:
        raise SystemExit(f"wheel is missing required members: {', '.join(missing)}")

    banned = [
        member
        for member in members
        if member.endswith(".db")
        or member.startswith(("data/", "models/"))
        or (member.endswith(".py") and "/" not in member)
    ]
    if banned:
        raise SystemExit(f"wheel contains forbidden members: {', '.join(sorted(banned))}")


def run_checked(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run an isolated command and surface its output on failure."""
    return subprocess.run(command, check=True, capture_output=True, text=True, cwd=cwd)


def validate_installed_wheel(wheel_path: Path) -> None:
    """Install without dependencies and exercise the public CLI contract."""
    with tempfile.TemporaryDirectory(prefix="isc-helwigii-wheel-") as temp_dir:
        environment = Path(temp_dir) / "venv"
        # Match `python -m venv` on POSIX. Relocatable uv runtimes need the original
        # executable path to locate their standard library when creating a venv.
        venv.EnvBuilder(with_pip=True, symlinks=os.name != 'nt').create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run_checked(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                str(wheel_path.resolve()),
            ]
        )

        imported = run_checked(
            [
                str(python),
                "-c",
                "import isc_helwigii; print(isc_helwigii.__version__)",
            ]
        ).stdout.strip()
        cli_version = run_checked(
            [str(python), "-m", "isc_helwigii.cli", "--version"]
        ).stdout.strip()
        if not imported or cli_version != imported:
            raise SystemExit(
                f"module CLI version mismatch: import={imported!r}, cli={cli_version!r}"
            )

        config = json.loads(
            run_checked([str(python), "-m", "isc_helwigii.cli", "config", "--json"]).stdout
        )
        required_keys = {"data_dir", "database_path", "export_dir", "image_dir"}
        if set(config) != required_keys:
            raise SystemExit(f"config keys differ: {sorted(config)}")
        project = Path(temp_dir) / "project.db"
        restored = Path(temp_dir) / "restored.db"
        bundle = Path(temp_dir) / "project.zip"
        cli = [str(python), "-m", "isc_helwigii.cli"]
        for arguments in (
            ["init", str(project)],
            ["demo", str(project)],
            ["export", str(project), str(bundle)],
            ["restore", str(bundle), str(restored)],
        ):
            run_checked(cli + arguments, cwd=Path(temp_dir))
        rows = json.loads(run_checked(cli + ["list", str(restored)], cwd=Path(temp_dir)).stdout)
        if len(rows) != 3:
            raise SystemExit("installed research workflow did not restore three demo witnesses")


def main(argv: list[str] | None = None) -> int:
    """Validate the wheel supplied as the only argument."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: check_wheel.py PATH_TO_WHEEL")
    wheel_path = Path(args[0])
    if not wheel_path.is_file():
        raise SystemExit(f"wheel does not exist: {wheel_path}")

    validate_members(wheel_path)
    validate_installed_wheel(wheel_path)
    sys.stdout.write(f"wheel contract passed: {wheel_path.name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
