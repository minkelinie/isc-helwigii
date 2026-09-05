import json
import zipfile

import pytest

from isc_helwigii.bundles import export_bundle, restore_bundle
from isc_helwigii.store import ResearchStore


def test_bundle_round_trip_and_existing_destination_protection(tmp_path):
    store = ResearchStore(tmp_path / "source.db")
    store.initialize()
    store.import_records(
        b"raw", [{"external_id": "a", "text": "a b"}], source="local", license="private"
    )
    artifact = store.artifacts()[0]["id"]
    store.add_asset(
        artifact, b"image", name="a.png", media_type="image/png", license="private", actor="me"
    )
    bundle = tmp_path / "bundle.zip"
    export_bundle(store, bundle)
    restored = restore_bundle(bundle, tmp_path / "restored.db")
    assert restored.dossier(artifact) == store.dossier(artifact)
    with pytest.raises(FileExistsError):
        restore_bundle(bundle, store.path)
    with pytest.raises(FileExistsError):
        export_bundle(store, bundle)


def test_tampered_bundle_leaves_no_project(tmp_path):
    bundle = tmp_path / "bad.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            "manifest.json", json.dumps({"format": "isc-research-bundle-v1", "sha256": "wrong"})
        )
        archive.writestr("project.sqlite3", b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        restore_bundle(bundle, tmp_path / "restore.db")
    assert not (tmp_path / "restore.db").exists()
