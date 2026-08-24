#!/usr/bin/env python3
"""
Cuneiform Polyphony Engine with Self-Improving Active Learning
Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii)
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("polyphony")

DB_PATH = Path("/data/cuneiform_master.db") if Path("/data/cuneiform_master.db").exists() else Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
POLYPHONY_PATH = Path("/data/cuneiform_polyphony.json") if Path("/data/cuneiform_polyphony.json").exists() else Path.home() / "Desktop" / "OxStealthData" / "cuneiform_polyphony.json"

@dataclass
class SignReading:
    sign_id: str
    unicode: str
    borger: str
    sumerian: List[str]
    akkadian: List[str]
    logographic: List[str]
    context_rules: List[Dict]
    frequency: int
    periods: List[str]

class PolyphonyEngine:
    """Cuneiform polyphony catalog with active learning feedback."""

    def __init__(self):
        self.signs: Dict[str, SignReading] = {}
        self.context_rules: List[Dict] = []
        self.compound_signs: List[Dict] = []
        self._init_db()
        self._load_polyphony_catalog()

    def _init_db(self):
        """Initialize database tables for active learning."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS polyphony_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sign_id TEXT NOT NULL,
                context TEXT NOT NULL,
                user_reading TEXT NOT NULL,
                user_translation TEXT,
                user_pos TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def _load_polyphony_catalog(self):
        """Load polyphony catalog from JSON."""
        with open(POLYPHONY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.context_rules = data.get('context_disambiguation_rules', [])
        self.compound_signs = data.get('compound_signs', [])

        for sign_id, sign_data in data.get('signs', {}).items():
            self.signs[sign_id] = SignReading(
                sign_id=sign_id,
                unicode=sign_data.get('unicode', ''),
                borger=sign_data.get('borger', ''),
                sumerian=sign_data.get('sumerian_readings', []),
                akkadian=sign_data.get('akkadian_readings', []),
                logographic=sign_data.get('logographic_values', []),
                context_rules=sign_data.get('context_rules', []),
                frequency=sign_data.get('frequency_rank', 999),
                periods=sign_data.get('periods', [])
            )
        log.info(f"Loaded {len(self.signs)} polyphonic signs")

    def get_readings(self, sign_id: str, context: Optional[str] = None) -> Dict:
        """Get all readings for a sign, optionally filtered by context."""
        if sign_id not in self.signs:
            return {"error": f"Sign {sign_id} not in catalog"}

        sign = self.signs[sign_id]
        result = {
            "sign_id": sign.sign_id,
            "unicode": sign.unicode,
            "sumerian": sign.sumerian,
            "akkadian": sign.akkadian,
            "logographic": sign.logographic,
            "context_rules": sign.context_rules
        }

        # Apply context rules if context provided
        if context:
            result['contextual_readings'] = self._apply_context_rules(sign, context)

        return result

    def _apply_context_rules(self, sign: SignReading, context: str) -> List[Dict]:
        """Apply context disambiguation rules."""
        readings = []
        for rule in sign.context_rules:
            # Simple pattern matching for context
            if rule.get('pattern', '').lower() in context.lower():
                readings.append({
                    "pattern": rule.get('pattern'),
                    "reading": rule.get('reading'),
                    "translation": rule.get('translation'),
                    "pos": rule.get('pos')
                })
        return readings

    def disambiguate_sequence(self, sign_sequence: List[str]) -> List[Dict]:
        """Disambiguate a sequence of signs using context rules."""
        results = []
        for i, sign_id in enumerate(sign_sequence):
            # Build context from surrounding signs
            left_context = sign_sequence[max(0, i-2):i]
            right_context = sign_sequence[i+1:min(len(sign_sequence), i+3)]
            context = " ".join(left_context + [sign_id] + right_context)

            sign_result = self.get_readings(sign_id, context)
            results.append(sign_result)
        return results

    def save_user_correction(self, sign_id: str, context: str,
                             user_reading: str, user_translation: str,
                             user_pos: str = "", confidence: float = 1.0) -> bool:
        """Save user correction for active learning."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS polyphony_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sign_id TEXT NOT NULL,
                    context TEXT NOT NULL,
                    user_reading TEXT NOT NULL,
                    user_translation TEXT,
                    user_pos TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    applied BOOLEAN DEFAULT 0
                )
            """)

            cur.execute("""
                INSERT INTO polyphony_corrections
                (sign_id, context, user_reading, user_translation, user_pos, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sign_id, context, user_reading, user_translation, user_pos, confidence))

            conn.commit()
            conn.close()

            # Update in-memory catalog with learned reading
            self._apply_learned_correction(sign_id, context, user_reading, user_translation, user_pos)

            log.info(f"Saved correction: {sign_id} in context '{context}' -> {user_reading}")
            return True
        except Exception as e:
            log.error(f"Failed to save correction: {e}")
            return False

    def _apply_learned_correction(self, sign_id: str, context: str,
                                  user_reading: str, user_translation: str, user_pos: str):
        """Apply learned correction to in-memory catalog."""
        if sign_id in self.signs:
            sign = self.signs[sign_id]
            # Add as new context rule
            sign.context_rules.append({
                "pattern": context,
                "reading": user_reading,
                "translation": user_translation,
                "pos": user_pos,
                "learned": True,
                "learned_at": datetime.now().isoformat()
            })
            log.info(f"Applied learned rule for {sign_id}: {context} -> {user_reading}")

    def get_pending_corrections(self) -> List[Dict]:
        """Get unapplied corrections from database."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, sign_id, context, user_reading, user_translation, user_pos, confidence, created_at
            FROM polyphony_corrections
            WHERE applied = 0
            ORDER BY created_at DESC
        """)

        rows = cur.fetchall()
        conn.close()

        return [
            {
                "id": r[0],
                "sign_id": r[1],
                "context": r[2],
                "user_reading": r[3],
                "user_translation": r[4],
                "user_pos": r[5],
                "confidence": r[6],
                "created_at": r[7]
            }
            for r in rows
        ]

    def apply_correction(self, correction_id: int) -> bool:
        """Mark correction as applied and update catalog."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT sign_id, context, user_reading, user_translation, user_pos FROM polyphony_corrections WHERE id = ?", (correction_id,))
        row = cur.fetchone()

        if row:
            self._apply_learned_correction(row[0], row[1], row[2], row[3], row[4])
            cur.execute("UPDATE polyphony_corrections SET applied = 1 WHERE id = ?", (correction_id,))
            conn.commit()
            conn.close()
            return True

        conn.close()
        return False

    def get_stats(self) -> Dict:
        """Get engine statistics."""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM polyphony_corrections")
        total_corrections = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM polyphony_corrections WHERE applied = 1")
        applied = cur.fetchone()[0]

        conn.close()

        return {
            "total_signs": len(self.signs),
            "total_context_rules": len(self.context_rules),
            "total_compounds": len(self.compound_signs),
            "user_corrections_total": total_corrections,
            "user_corrections_applied": applied,
            "pending_corrections": total_corrections - applied
        }

# Global instance
_polyphony_engine = None

def get_polyphony_engine() -> PolyphonyEngine:
    global _polyphony_engine
    if _polyphony_engine is None:
        _polyphony_engine = PolyphonyEngine()
    return _polyphony_engine

if __name__ == "__main__":
    engine = get_polyphony_engine()
    stats = engine.get_stats()
    print(json.dumps(stats, indent=2))