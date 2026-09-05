"""Portable project backups. Restore verifies before publishing a new destination."""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from isc_helwigii import __version__
from isc_helwigii.store import ResearchStore, canonical, now


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def export_bundle(store, destination):
    destination = Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("export destination already exists")
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".isc-export-") as temporary:
        backup = Path(temporary) / "project.sqlite3"
        with store.connection() as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        ResearchStore(backup).validate_contents()
        manifest = {
            "format": "isc-research-bundle-v1",
            "sha256": file_hash(backup),
            "software_version": __version__,
            "created_at": now(),
            "contains": "sources, editions, annotations, review history, media, experiments",
        }
        archive_path = Path(temporary) / "bundle.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(backup, "project.sqlite3")
            archive.writestr("manifest.json", canonical(manifest))
        os.link(archive_path, destination)
    return manifest


def restore_bundle(bundle, destination):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise FileExistsError("restore requires a new destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".isc-restore-") as temporary:
        backup = Path(temporary) / "project.sqlite3"
        with zipfile.ZipFile(bundle) as archive:
            if sorted(archive.namelist()) != ["manifest.json", "project.sqlite3"]:
                raise ValueError("unexpected bundle members")
            if (
                archive.getinfo("manifest.json").file_size > 1024 * 1024
                or archive.getinfo("project.sqlite3").file_size > 4 * 1024**3
            ):
                raise ValueError("bundle exceeds supported restore size")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "isc-research-bundle-v1":
                raise ValueError("unsupported bundle format")
            with archive.open("project.sqlite3") as source, backup.open("xb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
        if file_hash(backup) != manifest.get("sha256"):
            raise ValueError("bundle checksum mismatch")
        restored = ResearchStore(backup)
        restored.validate_contents()
        with restored.connection() as con:
            if (
                con.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or con.execute("PRAGMA foreign_key_check").fetchone()
            ):
                raise ValueError("database integrity check failed")
        os.link(backup, destination)
    return ResearchStore(destination)
