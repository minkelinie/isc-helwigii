#!/usr/bin/env python3
"""
Federated Corpus Registry — CDLI, ORACC, ETCSL Streaming Catalog
Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii)

Provides unified access to major cuneiform corpora with streaming catalog index.
"""

import sqlite3
import json
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator
from dataclasses import dataclass, asdict
from datetime import datetime
import logging
import hashlib

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("corpus_registry")

DB_PATH = Path("/data/cuneiform_master.db") if Path("/data/cuneiform_master.db").exists() else Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"

# Corpus endpoints
CORPUS_SOURCES = {
    "CDLI": {
        "name": "Cuneiform Digital Library Initiative",
        "base_url": "https://cdli.ucla.edu/",
        "api_url": "https://cdli.ucla.edu/search/atom",
        "search_url": "https://cdli.ucla.edu/search",
        "description": "Largest digital collection of cuneiform inscriptions (~400,000 objects)"
    },
    "ORACC": {
        "name": "Open Richly Annotated Cuneiform Corpus",
        "base_url": "https://oracc.museum.upenn.edu/",
        "api_url": "https://oracc.museum.upenn.edu/api/",
        "search_url": "https://oracc.museum.upenn.edu/corpus/",
        "description": "Richly annotated corpora with lemmatization and translations"
    },
    "ETCSL": {
        "name": "Electronic Text Corpus of Sumerian Literature",
        "base_url": "https://etcsl.orinst.ox.ac.uk/",
        "api_url": "https://etcsl.orinst.ox.ac.uk/api/",
        "search_url": "https://etcsl.orinst.ox.ac.uk/browse.html",
        "description": "Standard editions of Sumerian literary compositions"
    },
    "BDTNS": {
        "name": "Babylonian Divinatory Texts Network",
        "base_url": "https://bdtns.org/",
        "api_url": "https://bdtns.org/api/",
        "description": "Divinatory texts corpus (extispicy, astrology, etc.)"
    },
    "RINAP": {
        "name": "Royal Inscriptions of the Neo-Assyrian Period",
        "base_url": "https://rinap.ancientworldonline.org/",
        "description": "Neo-Assyrian royal inscriptions"
    },
    "RIMB": {
        "name": "Royal Inscriptions of Mesopotamia, Babylonian Periods",
        "base_url": "https://rimb.ancientworldonline.org/",
        "description": "Babylonian royal inscriptions"
    },
    "DCCLT": {
        "name": "Digital Corpus of Cuneiform Lexical Texts",
        "base_url": "https://dcclt.org/",
        "description": "Lexical lists and sign lists"
    },
    "GEM": {
        "name": "Global Egyptian Museum (for comparative studies)",
        "base_url": "https://www.globalegyptianmuseum.org/",
        "description": "Egyptian corpus for cross-cultural comparison"
    }
}

@dataclass
class CorpusEntry:
    """Single corpus catalog entry."""
    corpus_id: str
    object_id: str
    title: str
    period: str
    provenance: str
    genre: str
    language: str
    transliteration: Optional[str]
    translation: Optional[str]
    metadata_json: str
    cuneiform_text: Optional[str]
    image_url: Optional[str]
    atf_url: Optional[str]
    json_url: Optional[str]
    source_corpus: str
    accession_date: str
    content_hash: str

class CorpusRegistry:
    """Federated corpus registry with streaming catalog."""

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema for corpus catalog."""
        cur = self.conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS corpus_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                corpus_id TEXT NOT NULL,
                object_id TEXT NOT NULL,
                title TEXT,
                period TEXT,
                provenance TEXT,
                genre TEXT,
                language TEXT,
                transliteration TEXT,
                translation TEXT,
                metadata_json TEXT,
                cuneiform_text TEXT,
                image_url TEXT,
                atf_url TEXT,
                json_url TEXT,
                source_corpus TEXT NOT NULL,
                accession_date TEXT DEFAULT CURRENT_TIMESTAMP,
                content_hash TEXT,
                UNIQUE(corpus_id, object_id, source_corpus)
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_corpus_catalog_source
            ON corpus_catalog(source_corpus)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_corpus_catalog_period
            ON corpus_catalog(period)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_corpus_catalog_provenance
            ON corpus_catalog(provenance)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_corpus_catalog_genre
            ON corpus_catalog(genre)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_corpus_catalog_hash
            ON corpus_catalog(content_hash)
        """)

        # Corpus metadata table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS corpus_metadata (
                corpus_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_url TEXT,
                api_url TEXT,
                search_url TEXT,
                description TEXT,
                last_synced TEXT,
                total_objects INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        """)

        # Insert default corpus metadata
        for cid, info in CORPUS_SOURCES.items():
            cur.execute("""
                INSERT OR IGNORE INTO corpus_metadata
                (corpus_id, name, base_url, api_url, search_url, description, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            """, (cid, info['name'], info.get('base_url'), info.get('api_url'),
                  info.get('search_url'), info.get('description')))

        self.conn.commit()
        log.info("Corpus registry schema initialized")

    def _compute_hash(self, text: str) -> str:
        """Compute content hash for deduplication."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

    def add_entry(self, entry: CorpusEntry) -> bool:
        """Add or update a corpus entry."""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO corpus_catalog
                (corpus_id, object_id, title, period, provenance, genre, language,
                 transliteration, translation, metadata_json, cuneiform_text,
                 image_url, atf_url, json_url, source_corpus, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.corpus_id, entry.object_id, entry.title, entry.period,
                entry.provenance, entry.genre, entry.language,
                entry.transliteration, entry.translation, entry.metadata_json,
                entry.cuneiform_text, entry.image_url, entry.atf_url,
                entry.json_url, entry.source_corpus, entry.content_hash
            ))
            self.conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to add entry: {e}")
            return False

    def add_entries_batch(self, entries: List[CorpusEntry]) -> int:
        """Add multiple entries in batch."""
        cur = self.conn.cursor()
        added = 0
        for entry in entries:
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO corpus_catalog
                    (corpus_id, object_id, title, period, provenance, genre, language,
                     transliteration, translation, metadata_json, cuneiform_text,
                     image_url, atf_url, json_url, source_corpus, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.corpus_id, entry.object_id, entry.title, entry.period,
                    entry.provenance, entry.genre, entry.language,
                    entry.transliteration, entry.translation, entry.metadata_json,
                    entry.cuneiform_text, entry.image_url, entry.atf_url,
                    entry.json_url, entry.source_corpus, entry.content_hash
                ))
                if cur.rowcount > 0:
                    added += 1
            except Exception as e:
                log.warning(f"Failed to add {entry.object_id}: {e}")
        self.conn.commit()
        log.info(f"Batch added {added}/{len(entries)} entries")
        return added

    def get_entry(self, corpus_id: str, object_id: str, source: str) -> Optional[CorpusEntry]:
        """Get a specific corpus entry."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM corpus_catalog
            WHERE corpus_id = ? AND object_id = ? AND source_corpus = ?
        """, (corpus_id, object_id, source))
        row = cur.fetchone()
        if row:
            return CorpusEntry(*row[1:])  # Skip autoincrement id
        return None

    def search(self, query: str = "", source: Optional[str] = None,
               period: Optional[str] = None, provenance: Optional[str] = None,
               genre: Optional[str] = None, language: Optional[str] = None,
               limit: int = 100, offset: int = 0) -> List[CorpusEntry]:
        """Search corpus catalog with filters."""
        cur = self.conn.cursor()

        sql = "SELECT * FROM corpus_catalog WHERE 1=1"
        params = []

        if query:
            sql += " AND (title LIKE ? OR transliteration LIKE ? OR translation LIKE ?)"
            q = f"%{query}%"
            params.extend([q, q, q])

        if source:
            sql += " AND source_corpus = ?"
            params.append(source)

        if period:
            sql += " AND period = ?"
            params.append(period)

        if provenance:
            sql += " AND provenance LIKE ?"
            params.append(f"%{provenance}%")

        if genre:
            sql += " AND genre = ?"
            params.append(genre)

        if language:
            sql += " AND language = ?"
            params.append(language)

        sql += " ORDER BY accession_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur.execute(sql, params)
        rows = cur.fetchall()

        return [CorpusEntry(*row[1:]) for row in rows]

    def get_stats(self) -> Dict:
        """Get registry statistics."""
        cur = self.conn.cursor()

        cur.execute("SELECT COUNT(*) FROM corpus_catalog")
        total = cur.fetchone()[0]

        cur.execute("SELECT source_corpus, COUNT(*) FROM corpus_catalog GROUP BY source_corpus")
        by_source = dict(cur.fetchall())

        cur.execute("SELECT period, COUNT(*) FROM corpus_catalog WHERE period IS NOT NULL GROUP BY period ORDER BY period")
        by_period = dict(cur.fetchall())

        cur.execute("SELECT genre, COUNT(*) FROM corpus_catalog WHERE genre IS NOT NULL GROUP BY genre ORDER BY COUNT(*) DESC LIMIT 20")
        by_genre = dict(cur.fetchall())

        cur.execute("SELECT provenance, COUNT(*) FROM corpus_catalog WHERE provenance IS NOT NULL GROUP BY provenance ORDER BY COUNT(*) DESC LIMIT 20")
        by_provenance = dict(cur.fetchall())

        cur.execute("SELECT * FROM corpus_metadata")
        metadata = {}
        for row in cur.fetchall():
            metadata[row[0]] = {
                "name": row[1], "base_url": row[2], "api_url": row[3],
                "search_url": row[4], "description": row[5],
                "last_synced": row[6], "total_objects": row[7], "status": row[8]
            }

        return {
            "total_entries": total,
            "by_source": by_source,
            "by_period": by_period,
            "by_genre": by_genre,
            "by_provenance": by_provenance,
            "corpus_metadata": metadata
        }

    def stream_catalog(self, source: Optional[str] = None,
                       batch_size: int = 1000) -> Generator[List[CorpusEntry], None, None]:
        """Stream catalog entries in batches for memory-efficient processing."""
        cur = self.conn.cursor()

        sql = "SELECT * FROM corpus_catalog"
        params = []
        if source:
            sql += " WHERE source_corpus = ?"
            params.append(source)
        sql += " ORDER BY corpus_id, object_id"

        cur.execute(sql, params)

        batch = []
        for row in cur:
            batch.append(CorpusEntry(*row[1:]))
            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch

    def update_metadata(self, corpus_id: str, **kwargs) -> bool:
        """Update corpus metadata (last_synced, total_objects, etc.)."""
        try:
            cur = self.conn.cursor()
            updates = []
            values = []
            for k, v in kwargs.items():
                updates.append(f"{k} = ?")
                values.append(v)
            values.append(corpus_id)
            sql = f"UPDATE corpus_metadata SET {', '.join(updates)} WHERE corpus_id = ?"
            cur.execute(sql, values)
            self.conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to update metadata: {e}")
            return False

    def export_catalog(self, output_path: Path, format: str = "jsonl",
                       source: Optional[str] = None) -> int:
        """Export catalog to file (JSONL, CSV, or ATF)."""
        count = 0
        with open(output_path, 'w', encoding='utf-8') as f:
            for batch in self.stream_catalog(source, batch_size=1000):
                for entry in batch:
                    if format == "jsonl":
                        f.write(json.dumps(asdict(entry), ensure_ascii=False) + '\n')
                    elif format == "csv":
                        if count == 0:
                            # Write header
                            f.write(','.join([
                                'corpus_id', 'object_id', 'title', 'period', 'provenance',
                                'genre', 'language', 'source_corpus'
                            ]) + '\n')
                        f.write(','.join([
                            entry.corpus_id, entry.object_id, entry.title or '',
                            entry.period or '', entry.provenance or '',
                            entry.genre or '', entry.language or '',
                            entry.source_corpus
                        ]) + '\n')
                    elif format == "atf":
                        f.write(f"#atf: corpus={entry.source_corpus}\n")
                        f.write(f"#atf: object={entry.object_id}\n")
                        f.write(f"#atf: period={entry.period or 'unknown'}\n")
                        f.write(f"#atf: provenance={entry.provenance or 'unknown'}\n")
                        f.write(f"#atf: genre={entry.genre or 'unknown'}\n")
                        if entry.transliteration:
                            f.write(f"& {entry.transliteration}\n")
                        if entry.translation:
                            f.write(f"# translation: {entry.translation}\n")
                        f.write("\n")
                    count += 1
        log.info(f"Exported {count} entries to {output_path}")
        return count

# Convenience functions for common corpora (mock implementations for offline use)
def create_mock_cdli_entries(count: int = 100) -> List[CorpusEntry]:
    """Create mock CDLI entries for testing/demo."""
    entries = []
    periods = ['ED', 'EDIII', 'OLD_AKKADIAN', 'URIII', 'OB', 'MB', 'LB', 'NA', 'NB']
    provenances = ['Nippur', 'Ur', 'Larsa', 'Sippar', 'Babylon', 'Assur', 'Nineveh', 'Uruk']
    genres = ['administrative', 'literary', 'legal', 'lexical', 'royal', 'letter', 'mathematical']

    for i in range(count):
        period = periods[i % len(periods)]
        prov = provenances[i % len(provenances)]
        genre = genres[i % len(genres)]

        entry = CorpusEntry(
            corpus_id=f"P{i+1:06d}",
            object_id=f"P{i+1:06d}",
            title=f"Cuneiform tablet {genre} text from {prov}",
            period=period,
            provenance=prov,
            genre=genre,
            language='Sumerian' if i % 2 == 0 else 'Akkadian',
            transliteration=f"& ud {period.lower()} {prov.lower()} {genre} ...",
            translation=f"Tablet concerning {genre} matters from {prov} in {period} period.",
            metadata_json=json.dumps({"museum": "CDLI", "cdli_number": f"P{i+1:06d}"}),
            cuneiform_text=None,
            image_url=f"https://cdli.ucla.edu/dl/photo/P{i+1:06d}.jpg",
            atf_url=f"https://cdli.ucla.edu/atf/P{i+1:06d}.atf",
            json_url=f"https://cdli.ucla.edu/json/P{i+1:06d}.json",
            source_corpus="CDLI",
            accession_date=datetime.now().isoformat(),
            content_hash=""
        )
        entry.content_hash = hashlib.sha256(
            (entry.title + entry.transliteration + entry.translation).encode()
        ).hexdigest()[:16]
        entries.append(entry)
    return entries

def create_mock_oracc_entries(count: int = 50) -> List[CorpusEntry]:
    """Create mock ORACC entries for testing/demo."""
    entries = []
    projects = ['saao', 'rinap', 'rimb', 'dccs', 'cams', 'dcclt']
    periods = ['OB', 'MB', 'NA', 'NB', 'ACH']

    for i in range(count):
        project = projects[i % len(projects)]
        period = periods[i % len(periods)]

        entry = CorpusEntry(
            corpus_id=f"{project}_{i+1:04d}",
            object_id=f"{project}.{i+1:04d}",
            title=f"ORACC {project.upper()} text #{i+1}",
            period=period,
            provenance="Babylonia" if 'bab' in project else "Assyria",
            genre="royal" if 'rinap' in project or 'rimb' in project else "literary",
            language="Akkadian",
            transliteration=f"& {project} text {i+1} ...",
            translation=f"Translation of {project} text {i+1} from {period} period.",
            metadata_json=json.dumps({"project": project, "oracc_id": f"{project}.{i+1:04d}"}),
            cuneiform_text=None,
            image_url=f"https://oracc.museum.upenn.edu/{project}/images/{i+1:04d}.jpg",
            atf_url=f"https://oracc.museum.upenn.edu/{project}/atf/{i+1:04d}.atf",
            json_url=f"https://oracc.museum.upenn.edu/{project}/json/{i+1:04d}.json",
            source_corpus="ORACC",
            accession_date=datetime.now().isoformat(),
            content_hash=""
        )
        entry.content_hash = hashlib.sha256(
            (entry.title + entry.transliteration + entry.translation).encode()
        ).hexdigest()[:16]
        entries.append(entry)
    return entries

def create_mock_etcsl_entries(count: int = 30) -> List[CorpusEntry]:
    """Create mock ETCSL entries for testing/demo."""
    entries = []
    compositions = [
        "Gilgamesh and Aga", "Gilgamesh and Huwawa", "Gilgamesh and the Bull of Heaven",
        "Gilgamesh, Enkidu and the Netherworld", "Enmerkar and the Lord of Aratta",
        "Enmerkar and En-suhgir-ana", "Lugalbanda and the Anzu Bird",
        "Lugalbanda in the Mountain Cave", "The Debate between Bird and Fish",
        "The Debate between Winter and Summer", "The Debate between Cattle and Grain",
        "The Debate between the Hoe and the Plough", "Inanna and Ebih",
        "Inanna and Enki", "Inanna's Descent to the Netherworld",
        "The Exaltation of Inanna", "The Hymn to Ninkasi",
        "The Instructions of Shuruppak", "The Curse of Agade",
        "The Lament for Ur", "The Lament for Sumer and Ur"
    ]

    for i in range(min(count, len(compositions))):
        entry = CorpusEntry(
            corpus_id=f"c.{i+1}.{1}.{i+1}",
            object_id=f"c.{i+1}.{1}.{i+1}",
            title=compositions[i],
            period="OB",
            provenance="Nippur",
            genre="literary",
            language="Sumerian",
            transliteration=f"& {compositions[i].lower().replace(' ', '.')} ...",
            translation=f"Standard edition of {compositions[i]} from ETCSL.",
            metadata_json=json.dumps({"etcsl_id": f"c.{i+1}.{1}.{i+1}", "composer": "unknown"}),
            cuneiform_text=None,
            image_url=f"https://etcsl.orinst.ox.ac.uk/images/c{i+1}.jpg",
            atf_url=f"https://etcsl.orinst.ox.ac.uk/atf/c{i+1}.atf",
            json_url=f"https://etcsl.orinst.ox.ac.uk/json/c{i+1}.json",
            source_corpus="ETCSL",
            accession_date=datetime.now().isoformat(),
            content_hash=""
        )
        entry.content_hash = hashlib.sha256(
            (entry.title + entry.transliteration + entry.translation).encode()
        ).hexdigest()[:16]
        entries.append(entry)
    return entries

def populate_demo_data():
    """Populate registry with demo data from major corpora."""
    registry = CorpusRegistry()

    log.info("Populating demo data...")
    cdli_entries = create_mock_cdli_entries(200)
    oracc_entries = create_mock_oracc_entries(100)
    etcsl_entries = create_mock_etcsl_entries(30)

    total = 0
    total += registry.add_entries_batch(cdli_entries)
    total += registry.add_entries_batch(oracc_entries)
    total += registry.add_entries_batch(etcsl_entries)

    registry.update_metadata("CDLI", last_synced=datetime.now().isoformat(), total_objects=len(cdli_entries))
    registry.update_metadata("ORACC", last_synced=datetime.now().isoformat(), total_objects=len(oracc_entries))
    registry.update_metadata("ETCSL", last_synced=datetime.now().isoformat(), total_objects=len(etcsl_entries))

    log.info(f"Populated {total} total entries")
    return total

if __name__ == "__main__":
    total = populate_demo_data()
    print(f"Populated {total} corpus entries")

    registry = CorpusRegistry()
    stats = registry.get_stats()
    print(json.dumps(stats, indent=2, default=str))