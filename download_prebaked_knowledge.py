#!/usr/bin/env python3
"""
AUTO-FETCH KNOWLEDGE DISTRIBUTION SCRIPT
Download pre-baked embeddings, polyphony catalog, and sign knowledge on first start.
Enables zero-download federated corpus access with local caching.
"""

import os
import json
import logging
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import tempfile
import shutil
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
log = logging.getLogger("knowledge-fetcher")

# ———————————————————————————————————————————————————————————————
# Configuration
# ———————————————————————————————————————————————————————————————
VERSION = "2.0.0"
BASE_URL = os.getenv("ISC_HELWIGII_KNOWLEDGE_BASE_URL", "https://github.com/SignumCore/isc-helwigii/releases/download/prebaked-v2.0.0/")

# Files to download with expected SHA256 checksums (update after building release)
DOWNLOAD_MANIFEST = {
    "cuneiform_polyphony.json": {
        "url": BASE_URL + "cuneiform_polyphony.json",
        "sha256": None,  # Fill in after release
        "required": True,
        "description": "Full polyphony catalog with readings, context rules, compounds"
    },
    "prebaked_embeddings/faiss_index.bin": {
        "url": BASE_URL + "faiss_index.bin",
        "sha256": None,
        "required": False,  # Large file, optional
        "description": "FAISS index for fast similarity search"
    },
    "prebaked_embeddings/faiss_metadata.json": {
        "url": BASE_URL + "faiss_metadata.json",
        "sha256": None,
        "required": False,
        "description": "FAISS index metadata"
    },
    "prebaked_sign_knowledge.json": {
        "url": BASE_URL + "prebaked_sign_knowledge.json",
        "sha256": None,
        "required": True,
        "description": "Sign knowledge base (Unicode, Borger, readings, frequencies)"
    }
}

# Local paths
DATA_DIR = Path("/data") if Path("/data").exists() else Path.home() / "Desktop" / "OxStealthData"
DB_PATH = DATA_DIR / "cuneiform_master.db"
POLYPHONY_PATH = DATA_DIR / "cuneiform_polyphony.json"
PREBAKED_DIR = DATA_DIR / "prebaked_embeddings"
PREBAKED_DIR.mkdir(parents=True, exist_ok=True)

# Ensure DATA_DIR exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Knowledge state tracking
STATE_FILE = DATA_DIR / ".knowledge_state.json"

# ———————————————————————————————————————————————————————————————
# State Management
# ———————————————————————————————————————————————————————————————
def load_state() -> Dict[str, Any]:
    """Load knowledge fetch state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "version": None,
        "files_downloaded": {},
        "last_check": None,
        "db_populated": False
    }


def save_state(state: Dict[str, Any]):
    """Save knowledge fetch state."""
    state["last_check"] = time.time()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def verify_checksum(filepath: Path, expected_sha256: Optional[str]) -> bool:
    """Verify file SHA256 checksum."""
    if expected_sha256 is None:
        return True  # Skip verification if no checksum provided

    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest() == expected_sha256


# ———————————————————————————————————————————————————————————————
# Download Functions
# ———————————————————————————————————————————————————————————————
def download_file(url: str, dest_path: Path, max_retries: int = 3, timeout: int = 120) -> bool:
    """Download file with retries and progress."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        try:
            log.info(f"  Downloading {dest_path.name} (attempt {attempt + 1}/{max_retries})...")

            req = Request(url, headers={'User-Agent': f'ISC-Helwigii/{VERSION}'})
            with urlopen(req, timeout=timeout) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0

                with open(dest_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            pct = (downloaded / total_size) * 100
                            if downloaded % (1024 * 1024) == 0:  # Log every MB
                                log.info(f"    Progress: {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB)")

            log.info(f"  ✓ Downloaded {dest_path.name} ({downloaded / 1024 / 1024:.1f} MB)")
            return True

        except HTTPError as e:
            log.error(f"  HTTP Error: {e.code} {e.reason}")
            if e.code == 404:
                break  # Not found, don't retry
        except URLError as e:
            log.error(f"  URL Error: {e.reason}")
        except Exception as e:
            log.error(f"  Error: {e}")

        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            log.info(f"  Retrying in {wait_time}s...")
            time.sleep(wait_time)

    return False


def download_all_knowledge(force: bool = False) -> Dict[str, bool]:
    """Download all pre-baked knowledge files."""
    state = load_state()

    # Skip if already at current version and not forced
    if not force and state.get("version") == VERSION:
        all_present = all(
            (DATA_DIR / fname).exists()
            for fname, info in DOWNLOAD_MANIFEST.items()
            if info["required"]
        )
        if all_present:
            log.info("✓ Knowledge already at current version, skipping download")
            return {fname: True for fname in DOWNLOAD_MANIFEST}

    log.info("=" * 70)
    log.info(f"📦 AUTO-FETCH PRE-BAKED KNOWLEDGE (v{VERSION})")
    log.info("=" * 70)
    log.info(f"Source: {BASE_URL}")

    results = {}

    for fname, info in DOWNLOAD_MANIFEST.items():
        dest = DATA_DIR / fname

        # Skip if already exists and not forced
        if not force and dest.exists() and fname in state.get("files_downloaded", {}):
            log.info(f"  ⏭️  {fname} already present, skipping")
            results[fname] = True
            continue

        if not info["required"] and not force:
            log.info(f"  ⏭️  {fname} optional, skipping (use --force to download)")
            results[fname] = True
            continue

        log.info(f"  📥 {fname} - {info['description']}")
        success = download_file(info["url"], dest)

        if success and info["sha256"]:
            if not verify_checksum(dest, info["sha256"]):
                log.error(f"  ❌ Checksum mismatch for {fname}")
                dest.unlink(missing_ok=True)
                success = False

        results[fname] = success

        if success:
            state.setdefault("files_downloaded", {})[fname] = {
                "downloaded_at": time.time(),
                "size": dest.stat().st_size
            }

    # Update state
    state["version"] = VERSION
    save_state(state)

    success_count = sum(1 for v in results.values() if v)
    required_failed = any(not results.get(fname, True) for fname, info in DOWNLOAD_MANIFEST.items() if info["required"])

    if required_failed:
        log.error("❌ Some required files failed to download")
    else:
        log.info(f"✅ Downloaded {success_count}/{len(results)} files")

    return results


# ———————————————————————————————————————————————————————————————
# Database Population from Downloads
# ———————————————————————————————————————————————————————————————
def populate_db_from_downloads(conn: sqlite3.Connection) -> bool:
    """Populate database tables from downloaded knowledge files."""
    log.info("🗄️ Populating database from downloaded knowledge...")

    cur = conn.cursor()

    # 1. Load polyphony catalog
    if POLYPHONY_PATH.exists():
        log.info("  Loading polyphony catalog...")
        with open(POLYPHONY_PATH, 'r', encoding='utf-8') as f:
            polyphony = json.load(f)

        # Populate prebaked_sign_knowledge table
        for sign_id, sign_data in polyphony.get('signs', {}).items():
            cur.execute("""
                INSERT OR REPLACE INTO prebaked_sign_knowledge
                (sign_id, unicode, borger_number, name,
                 sumerian_readings, akkadian_readings, logographic_values,
                 periods, corpus_frequency, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sign_id,
                sign_data.get('unicode', ''),
                sign_data.get('borger', ''),
                sign_data.get('name', sign_id),
                json.dumps(sign_data.get('sumerian_readings', [])),
                json.dumps(sign_data.get('akkadian_readings', [])),
                json.dumps(sign_data.get('logographic_values', [])),
                json.dumps(sign_data.get('periods', [])),
                sign_data.get('corpus_frequency', 0),
                1.0 if sign_data.get('observed_in_corpus', False) else 0.5
            ))

        conn.commit()
        log.info(f"    ✓ Populated {len(polyphony.get('signs', {}))} sign entries")

    # 2. Load sign knowledge export (if separate file exists)
    sign_knowledge_path = DATA_DIR / "prebaked_sign_knowledge.json"
    if sign_knowledge_path.exists():
        log.info("  Loading additional sign knowledge...")
        with open(sign_knowledge_path, 'r', encoding='utf-8') as f:
            sign_knowledge = json.load(f)

        for entry in sign_knowledge.get('signs', []):
            cur.execute("""
                INSERT OR REPLACE INTO prebaked_sign_knowledge
                (sign_id, unicode, borger_number, name,
                 sumerian_readings, akkadian_readings, logographic_values,
                 periods, corpus_frequency, confidence_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.get('sign_id'),
                entry.get('unicode', ''),
                entry.get('borger_number', ''),
                entry.get('name', ''),
                json.dumps(entry.get('sumerian_readings', [])),
                json.dumps(entry.get('akkadian_readings', [])),
                json.dumps(entry.get('logographic_values', [])),
                json.dumps(entry.get('periods', [])),
                entry.get('corpus_frequency', 0),
                entry.get('confidence_score', 1.0)
            ))

        conn.commit()
        log.info(f"    ✓ Populated {len(sign_knowledge.get('signs', []))} additional sign entries")

    # 3. Mark FAISS index as available (files are used directly, not stored in DB)
    faiss_index = PREBAKED_DIR / "faiss_index.bin"
    faiss_meta = PREBAKED_DIR / "faiss_metadata.json"
    if faiss_index.exists() and faiss_meta.exists():
        log.info("  ✓ FAISS index files present")
        with open(faiss_meta, 'r') as f:
            meta = json.load(f)
        log.info(f"    Index: {meta.get('count', 0)} vectors, dim={meta.get('dim', 0)}")

    return True


# ———————————————————————————————————————————————————————————————
# Main Entry Point
# ———————————————————————————————————————————————————————————————
def ensure_knowledge_available(force_download: bool = False) -> bool:
    """
    Main entry point: ensure all pre-baked knowledge is available locally.
    Call this at application startup.
    """
    log.info("=" * 70)
    log.info("🔍 CHECKING PRE-BAKED KNOWLEDGE AVAILABILITY")
    log.info("=" * 70)

    # Check required files
    required_files = [fname for fname, info in DOWNLOAD_MANIFEST.items() if info["required"]]
    missing_required = [f for f in required_files if not (DATA_DIR / f).exists()]

    if missing_required:
        log.info(f"Missing required files: {missing_required}")
        results = download_all_knowledge(force=force_download)

        if not all(results.get(f, False) for f in required_files):
            log.error("❌ Failed to acquire required knowledge files")
            return False

    # Populate database
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        populate_db_from_downloads(conn)
        conn.close()
    except Exception as e:
        log.error(f"❌ Database population failed: {e}")
        return False

    log.info("=" * 70)
    log.info("✅ ALL KNOWLEDGE READY")
    log.info("=" * 70)
    return True


def export_sign_knowledge_json(output_path: Path = None):
    """Export prebaked_sign_knowledge table to JSON for release bundling."""
    if output_path is None:
        output_path = DATA_DIR / "prebaked_sign_knowledge.json"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM prebaked_sign_knowledge ORDER BY sign_id")
    rows = cur.fetchall()

    export_data = {
        "version": VERSION,
        "exported_at": time.time(),
        "count": len(rows),
        "signs": []
    }

    for row in rows:
        export_data["signs"].append({
            "sign_id": row['sign_id'],
            "unicode": row['unicode'],
            "borger_number": row['borger_number'],
            "name": row['name'],
            "sumerian_readings": json.loads(row['sumerian_readings']) if row['sumerian_readings'] else [],
            "akkadian_readings": json.loads(row['akkadian_readings']) if row['akkadian_readings'] else [],
            "logographic_values": json.loads(row['logographic_values']) if row['logographic_values'] else [],
            "periods": json.loads(row['period_attestations']) if row['period_attestations'] else [],
            "corpus_frequency": row['corpus_frequency'],
            "confidence_score": row['confidence_score']
        })

    conn.close()

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    log.info(f"✓ Exported sign knowledge to {output_path} ({len(rows)} signs)")
    return export_data


if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv
    export = "--export-sign-knowledge" in sys.argv

    if export:
        export_sign_knowledge_json()
    else:
        success = ensure_knowledge_available(force_download=force)
        exit(0 if success else 1)