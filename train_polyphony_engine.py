#!/usr/bin/env python3
"""
FULL CORPUS POLYPHONY & CONTEXT BAKE
Train the Polyphony Engine on all available CDLI/ORACC/ETCSL data.

Collects all sign readings from transliterations, computes n-gram context probabilities,
and generates comprehensive cuneiform_polyphony.json with logographic meanings.
"""

import sqlite3
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
log = logging.getLogger("polyphony-trainer")

# Use /data in container, ~/Desktop/OxStealthData/data on host
if Path("/data").exists():
    DB_PATH = Path("/data/cuneiform_master.db")
    POLYPHONY_OUTPUT = Path("/data/cuneiform_polyphony.json")
else:
    DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
    POLYPHONY_OUTPUT = Path.home() / "Desktop" / "OxStealthData" / "data" / "cuneiform_polyphony.json"
    POLYPHONY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────
# Borger Sign List Mapping (Complete Core Set)
# ──────────────────────────────────────────────────────────────
BORGER_SIGN_LIST = {
    # Core high-frequency signs with Unicode, Borger numbers, and readings
    "A": {"unicode": "𒀀", "borger": "1", "name": "A (water/arm)", "logographic": ["A", "A", "A", "A", "A", "A"]},
    "AN": {"unicode": "𒀭", "borger": "24", "name": "AN (heaven/god)", "logographic": ["AN", "DINGIR", "ILU"]},
    "DINGIR": {"unicode": "𒀭", "borger": "24", "name": "DINGIR (god determinative)", "logographic": ["DINGIR", "AN"]},
    "EN": {"unicode": "𒂗", "borger": "152", "name": "EN (lord/priest)", "logographic": ["EN"]},
    "KI": {"unicode": "𒆠", "borger": "214", "name": "KI (earth/place)", "logographic": ["KI", "E2"]},
    "LUGAL": {"unicode": "𒈗", "borger": "577", "name": "LUGAL (king)", "logographic": ["LUGAL", "SAR"]},
    "NI": {"unicode": "𒉌", "borger": "712", "name": "NI (self/fear)", "logographic": ["NI"]},
    "URU": {"unicode": "𒌷", "borger": "305", "name": "URU (city)", "logographic": ["URU", "ALU"]},
    "MA": {"unicode": "𒈠", "borger": "163", "name": "MA (ship/land)", "logographic": ["MA", "AS"]},
    "E2": {"unicode": "𒂍", "borger": "32", "name": "E2 (house/temple)", "logographic": ["E2", "BI2"]},
    # Extended set from sign detection
    "WEDGE": {"unicode": "𒁹", "borger": "582", "name": "WEDGE (basic)", "logographic": ["1", "DIS"]},
    "VERTICAL": {"unicode": "𒁹", "borger": "582", "name": "VERTICAL (DIŠ)", "logographic": ["DIS", "1"]},
    "HORIZONTAL": {"unicode": "𒀸", "borger": "582", "name": "HORIZONTAL (AŠ)", "logographic": ["AS", "10"]},
    "ANGLED": {"unicode": "𒂊", "borger": "583", "name": "ANGLED wedge", "logographic": ["E", "E"]},
    "COMPLEX": {"unicode": "𒆜", "borger": "154", "name": "COMPLEX (KASKAL)", "logographic": ["KASKAL"]},
    "SAG": {"unicode": "𒊕", "borger": "184", "name": "SAG (head)", "logographic": ["SAG", "RAS"]},
    "DUB": {"unicode": "𒁾", "borger": "150", "name": "DUB (tablet)", "logographic": ["DUB", "TUPPU"]},
    "KA": {"unicode": "𒅗", "borger": "213", "name": "KA (mouth)", "logographic": ["KA", "PU"]},
    "UD": {"unicode": "𒌓", "borger": "450", "name": "UD (sun/day)", "logographic": ["UD", "UTU", "YAM"]},
    "UNUG": {"unicode": "𒀕", "borger": "120", "name": "UNUG (Uruk)", "logographic": ["UNUG", "URUK"]},
    "GAL": {"unicode": "𒃲", "borger": "363", "name": "GAL (great)", "logographic": ["GAL", "RABU"]},
    "NUN": {"unicode": "𒉣", "borger": "217", "name": "NUN (prince)", "logographic": ["NUN"]},
    "ZU": {"unicode": "𒍪", "borger": "377", "name": "ZU (to know)", "logographic": ["ZU"]},
    "NA": {"unicode": "𒈾", "borger": "222", "name": "NA (man/incense)", "logographic": ["NA"]},
    "MEŠ": {"unicode": "𒈨𒌍", "borger": "552", "name": "MEŠ (plural)", "logographic": ["MES", "HI.A"]},
    "GIŠ": {"unicode": "𒄑", "borger": "267", "name": "GIŠ (wood/tree)", "logographic": ["GIS", "ISU"]},
    "MU": {"unicode": "𒈬", "borger": "159", "name": "MU (name/year)", "logographic": ["MU", "SIM"]},
    "BI": {"unicode": "𒁉", "borger": "86", "name": "BI (to speak)", "logographic": ["BI"]},
    "DU": {"unicode": "𒁺", "borger": "72", "name": "DU (to go)", "logographic": ["DU", "ALAK"]},
    "GA": {"unicode": "𒂵", "borger": "261", "name": "GA (milk/carry)", "logographic": ["GA"]},
    "HA": {"unicode": "𒄩", "borger": "289", "name": "HA (fish)", "logographic": ["HA", "KU"]},
    "LA": {"unicode": "𒆷", "borger": "349", "name": "LA (to hang)", "logographic": ["LA"]},
    "LI": {"unicode": "𒇷", "borger": "462", "name": "LI (oil)", "logographic": ["LI", "I"]},
    "MAH": {"unicode": "𒈤", "borger": "169", "name": "MAH (great/exalted)", "logographic": ["MAH"]},
    "MIN": {"unicode": "𒈫", "borger": "173", "name": "MIN (two)", "logographic": ["MIN", "SENA"]},
    "NAM": {"unicode": "𒉆", "borger": "232", "name": "NAM (destiny)", "logographic": ["NAM", "SIMAT"]},
    "NI2": {"unicode": "𒉈", "borger": "713", "name": "NI2 (fear)", "logographic": ["NI2"]},
    "NIN": {"unicode": "𒎏", "borger": "221", "name": "NIN (lady/queen)", "logographic": ["NIN", "BELTU"]},
    "NINDA": {"unicode": "𒃻", "borger": "398", "name": "NINDA (bread)", "logographic": ["NINDA", "AKALU"]},
    "PA": {"unicode": "𒉺", "borger": "240", "name": "PA (chief)", "logographic": ["PA", "RABU"]},
    "RA": {"unicode": "𒊏", "borger": "251", "name": "RA (to beat)", "logographic": ["RA", "MAHASU"]},
    "RE": {"unicode": "𒊑", "borger": "254", "name": "RE (to send)", "logographic": ["RE"]},
    "RI": {"unicode": "𒊑", "borger": "254", "name": "RI (to send)", "logographic": ["RI"]},
    "RU": {"unicode": "𒊒", "borger": "260", "name": "RU (to dedicate)", "logographic": ["RU"]},
    "SA": {"unicode": "𒊓", "borger": "265", "name": "SA (sinew/muscle)", "logographic": ["SA", "GID"]},
    "SE": {"unicode": "𒋛", "borger": "283", "name": "SE (grain/barley)", "logographic": ["SE", "SE"]},
    "SI": {"unicode": "𒋛", "borger": "283", "name": "SI (horn)", "logographic": ["SI", "QARNU"]},
    "SU": {"unicode": "𒋢", "borger": "285", "name": "SU (hand)", "logographic": ["SU", "QATU"]},
    "TA": {"unicode": "𒋫", "borger": "313", "name": "TA (dagger)", "logographic": ["TA", "PATU"]},
    "TI": {"unicode": "𒋾", "borger": "321", "name": "TI (arrow/life)", "logographic": ["TI", "BALATU"]},
    "TU": {"unicode": "𒌅", "borger": "448", "name": "TU (to beat)", "logographic": ["TU", "MAHASU"]},
    "U": {"unicode": "𒌋", "borger": "582", "name": "U (ten)", "logographic": ["U", "AS"]},
    "U2": {"unicode": "𒌋𒌋", "borger": "582", "name": "U2 (plant)", "logographic": ["U2"]},
    "U3": {"unicode": "𒀇", "borger": "3", "name": "U3 (sleep)", "logographic": ["U3"]},
    "U4": {"unicode": "𒌓", "borger": "450", "name": "U4 (day/UD)", "logographic": ["U4", "UD"]},
    "U5": {"unicode": "𒁁", "borger": "67", "name": "U5 (to ride)", "logographic": ["U5"]},
    "UR": {"unicode": "𒌨", "borger": "305", "name": "UR (dog/lion)", "logographic": ["UR", "UR"]},
    "US": {"unicode": "𒍑", "borger": "358", "name": "US (to follow)", "logographic": ["US"]},
    "ZA": {"unicode": "𒍝", "borger": "368", "name": "ZA (gem/bead)", "logographic": ["ZA"]},
    "ZI": {"unicode": "𒍣", "borger": "372", "name": "ZI (to rise)", "logographic": ["ZI", "BALATU"]},
    "ZU2": {"unicode": "𒍫", "borger": "378", "name": "ZU2 (tooth)", "logographic": ["ZU2", "SU"]},
}

# ──────────────────────────────────────────────────────────────
# Context Rule Templates (for auto-generation)
# ──────────────────────────────────────────────────────────────
CONTEXT_RULE_TEMPLATES = [
    # Determinatives
    {"pattern": r"^(DINGIR|AN)\.(?!\.)", "action": "add_divine_determinative", "priority": 100,
     "description": "Divine determinative before deity name"},
    {"pattern": r"\.(KI|URU)$", "action": "add_geo_determinative", "priority": 90,
     "description": "Geographic determinative after place name"},
    {"pattern": r"^GIŠ\.(?!\.)", "action": "add_wood_determinative", "priority": 80,
     "description": "Wood determinative before object"},
    {"pattern": r"\.MEŠ$", "action": "add_plural_marker", "priority": 70,
     "description": "Plural marker after noun"},

    # Common compound patterns
    {"pattern": r"LUGAL\.KALAM", "reading": "lugal.kalam", "translation": "king of the land", "pos": "N", "priority": 95},
    {"pattern": r"LUGAL\.UGU", "reading": "lugal.ugu", "translation": "overlord", "pos": "N", "priority": 95},
    {"pattern": r"NAM\.LUGAL", "reading": "nam.lugal", "translation": "kingship", "pos": "N", "priority": 95},
    {"pattern": r"EN\.LIL", "reading": "en.lil2", "translation": "Enlil", "pos": "PN", "priority": 95},
    {"pattern": r"EN\.KI", "reading": "en.ki", "translation": "Enki", "pos": "PN", "priority": 95},
    {"pattern": r"E2\.GAL", "reading": "e2.gal", "translation": "palace", "pos": "N", "priority": 90},
    {"pattern": r"E2\.DUB\.BA", "reading": "e2.dub.ba", "translation": "archives", "pos": "N", "priority": 90},
    {"pattern": r"E2\.KUR\.RA", "reading": "e2.kur.ra", "translation": "mountain house/temple", "pos": "N", "priority": 90},
    {"pattern": r"URU\.SAG", "reading": "uru.sag", "translation": "capital city", "pos": "N", "priority": 90},
    {"pattern": r"URU\.KI", "reading": "uru.ki", "translation": "city", "pos": "N", "priority": 90},
    {"pattern": r"AN\.KI", "reading": "an.ki", "translation": "universe/heaven-earth", "pos": "N", "priority": 95},
    {"pattern": r"AN\.NA", "reading": "an.na", "translation": "to heavens", "pos": "ADV", "priority": 85},
    {"pattern": r"DINGIR\.GAL", "reading": "dingir.gal", "translation": "great god", "pos": "N", "priority": 90},
    {"pattern": r"DINGIR\.MEŠ", "reading": "dingir.meš", "translation": "gods", "pos": "N", "priority": 90},
    {"pattern": r"KI\.GAL", "reading": "ki.gal", "translation": "great earth", "pos": "N", "priority": 85},
    {"pattern": r"KI\.EN\.GI", "reading": "ki.en.gi", "translation": "Sumer", "pos": "GN", "priority": 95},
    {"pattern": r"MA\.AN\.SUM", "reading": "ma.an.sum", "translation": "goddess Mamu", "pos": "DN", "priority": 80},
    {"pattern": r"MA\.GAN", "reading": "ma.gan", "translation": "ship", "pos": "N", "priority": 80},
    {"pattern": r"NI\.GUR", "reading": "ni.gur", "translation": "to turn back", "pos": "V", "priority": 85},
    {"pattern": r"NI\.TA", "reading": "ni.ta", "translation": "fear", "pos": "N", "priority": 85},
    {"pattern": r"EN\.GAG", "reading": "en.gag", "translation": "high priest", "pos": "N", "priority": 85},
    {"pattern": r"A\.GAL", "reading": "a.gal", "translation": "great arm/power", "pos": "N", "priority": 80},
    {"pattern": r"A\.NUN", "reading": "a.nun", "translation": "princely arm", "pos": "N", "priority": 80},
    {"pattern": r"A\.ZU", "reading": "a.zu", "translation": "knowing arm/knowledge", "pos": "N", "priority": 80},
]

# Common compound signs from literature
COMPOUND_SIGNS = [
    {"components": ["SAG", "DU"], "composite": "SAG.DU", "reading": "sag.du", "translation": "head/leader", "borger": "compound_001"},
    {"components": ["KA", "DUB"], "composite": "KA.DUB", "reading": "ka.dub", "translation": "mouth/tablet = scribe", "borger": "compound_002"},
    {"components": ["UD", "UNUG"], "composite": "UD.UNUG", "reading": "ud.unug", "translation": "day/Uruk = daily", "borger": "compound_003"},
    {"components": ["LUGAL", "KALAM", "MA"], "composite": "LUGAL.KALAM.MA", "reading": "lugal.kalam.ma", "translation": "king of the land", "borger": "compound_004"},
    {"components": ["EN", "LIL"], "composite": "EN.LIL", "reading": "en.lil2", "translation": "Enlil", "borger": "compound_005"},
    {"components": ["EN", "KI"], "composite": "EN.KI", "reading": "en.ki", "translation": "Enki", "borger": "compound_006"},
    {"components": ["NIN", "HUR"], "composite": "NIN.HUR", "reading": "nin.hur", "translation": "Ninhursag", "borger": "compound_007"},
    {"components": ["DINGIR", "NIN", "LIL"], "composite": "DINGIR.NIN.LIL", "reading": "dingir.nin.lil", "translation": "divine Ninlil", "borger": "compound_008"},
    {"components": ["E2", "GAL"], "composite": "E2.GAL", "reading": "e2.gal", "translation": "palace", "borger": "compound_009"},
    {"components": ["E2", "DUB", "BA"], "composite": "E2.DUB.BA", "reading": "e2.dub.ba", "translation": "archives", "borger": "compound_010"},
    {"components": ["AN", "NA"], "composite": "AN.NA", "reading": "an.na", "translation": "to heaven", "borger": "compound_011"},
    {"components": ["KI", "EN", "GI"], "composite": "KI.EN.GI", "reading": "ki.en.gi", "translation": "Sumer", "borger": "compound_012"},
    {"components": ["URU", "SAG"], "composite": "URU.SAG", "reading": "uru.sag", "translation": "capital city", "borger": "compound_013"},
    {"components": ["MA", "AN", "SUM"], "composite": "MA.AN.SUM", "reading": "ma.an.sum", "translation": "goddess Mamu", "borger": "compound_014"},
    {"components": ["NIN", "DA"], "composite": "NIN.DA", "reading": "nin.da", "translation": "Ninda (goddess)", "borger": "compound_015"},
]

# ──────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────
def extract_sign_tokens(transliteration: str) -> List[str]:
    """Extract individual sign tokens from ATF transliteration."""
    if not transliteration:
        return []

    # Remove ATF markers
    text = transliteration
    text = re.sub(r'^[&#@]\s*', '', text)  # Remove line prefixes
    text = re.sub(r'#.*$', '', text, flags=re.MULTILINE)  # Remove comments

    # Split by dots and spaces, keeping compound signs together
    tokens = []
    for part in text.split():
        # Further split on dots for individual signs in compounds
        sub_tokens = [t for t in part.split('.') if t]
        tokens.extend(sub_tokens)

    # Clean tokens
    cleaned = []
    for token in tokens:
        # Remove numeric subscripts (e.g., "a2" -> "a", "an5" -> "an")
        clean = re.sub(r'\d+$', '', token)
        # Remove parentheses and brackets
        clean = re.sub(r'[()\[\]{}]', '', clean)
        # Remove determinative markers
        clean = clean.replace('d', '').replace('giš', '').replace('ki', '').replace('uru', '')
        clean = clean.strip()
        if clean and len(clean) > 0 and not clean.isdigit():
            cleaned.append(clean.upper())

    return cleaned


def build_sign_cooccurrence_matrix(transliterations: List[str], window: int = 2) -> Dict[str, Dict[str, int]]:
    """Build sign co-occurrence matrix for n-gram probability estimation."""
    cooc = defaultdict(Counter)
    total_signs = Counter()

    for translit in transliterations:
        tokens = extract_sign_tokens(translit)
        total_signs.update(tokens)

        # Build n-grams
        for i, token in enumerate(tokens):
            # Look at window around token
            start = max(0, i - window)
            end = min(len(tokens), i + window + 1)
            context = tokens[start:i] + tokens[i+1:end]

            for ctx_token in context:
                cooc[token][ctx_token] += 1

    return {k: dict(v) for k, v in cooc.items()}, total_signs


def compute_context_probabilities(cooc_matrix: Dict[str, Dict[str, int]],
                                   total_counts: Counter) -> Dict[str, Dict[str, float]]:
    """Compute P(context|sign) probabilities for disambiguation."""
    probs = {}
    for sign, contexts in cooc_matrix.items():
        sign_total = total_counts.get(sign, 1)
        probs[sign] = {ctx: count / sign_total for ctx, count in contexts.items()}
    return probs


def parse_atf_corpus(transliteration: str) -> List[str]:
    """Parse ATF format and extract clean sign sequences."""
    signs = extract_sign_tokens(transliteration)
    return signs


# ──────────────────────────────────────────────────────────────
# Main Training Function
# ──────────────────────────────────────────────────────────────
def train_polyphony_from_corpus() -> Dict[str, Any]:
    """Main training pipeline: extract all readings from corpus, build polyphony catalog."""

    log.info("=" * 70)
    log.info("🏛️  FULL CORPUS POLYPHONY & CONTEXT BAKE")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1️⃣ Collect all transliterations from all sources
    log.info("📚 Collecting transliterations from all corpora...")

    all_transliterations = []
    source_stats = {}

    # From tablets (CDLI + user uploaded)
    cur.execute("SELECT transliteration, cuneiform as translation, p_number, source, period FROM tablets WHERE transliteration IS NOT NULL AND transliteration != ''")
    tablets = cur.fetchall()
    for row in tablets:
        if row['transliteration']:
            all_transliterations.append(row['transliteration'])
            src = row['source'] or 'tablets'
            source_stats[src] = source_stats.get(src, 0) + 1

    # From myth_texts
    cur.execute("SELECT transliteration, translation, corpus_source, period FROM myth_texts WHERE transliteration IS NOT NULL AND transliteration != ''")
    myths = cur.fetchall()
    for row in myths:
        if row['transliteration']:
            all_transliterations.append(row['transliteration'])
            src = row['corpus_source'] or 'myth_texts'
            source_stats[src] = source_stats.get(src, 0) + 1

    # From corpus_catalog (CDLI/ORACC/ETCSL)
    cur.execute("SELECT transliteration, translation, source_corpus, period FROM corpus_catalog WHERE transliteration IS NOT NULL AND transliteration != ''")
    corpus_entries = cur.fetchall()
    for row in corpus_entries:
        if row['transliteration']:
            all_transliterations.append(row['transliteration'])
            src = row['source_corpus'] or 'corpus_catalog'
            source_stats[src] = source_stats.get(src, 0) + 1

    log.info(f"  Collected {len(all_transliterations)} transliterations")
    for src, count in source_stats.items():
        log.info(f"    {src}: {count}")

    # 2️⃣ Build co-occurrence matrix
    log.info("🔢 Building n-gram co-occurrence matrix...")
    cooc_matrix, total_counts = build_sign_cooccurrence_matrix(all_transliterations, window=3)

    # 3️⃣ Compute context probabilities
    log.info("📊 Computing context probabilities (P(context|sign))...")
    context_probs = compute_context_probabilities(cooc_matrix, total_counts)

    # 4️⃣ Extract all unique signs observed in corpus
    observed_signs = set()
    for tokens in [extract_sign_tokens(t) for t in all_transliterations]:
        observed_signs.update(tokens)

    log.info(f"  Unique signs observed in corpus: {len(observed_signs)}")

    # 5️⃣ Build comprehensive polyphony catalog
    log.info("📖 Building comprehensive polyphony catalog...")

    polyphony_catalog = {
        "version": "3.0",
        "platform": "Interpres scripturae cuneiformis Helwigii (I.S.C. Helwigii)",
        "description": "Full-corpus trained polyphony catalog — Sumerian/Akkadian readings, logographic values, n-gram context probabilities, and compound signs",
        "training_stats": {
            "transliterations_analyzed": len(all_transliterations),
            "unique_signs_observed": len(observed_signs),
            "total_sign_tokens": sum(total_counts.values()),
            "context_windows": 3,
            "sources": source_stats
        },
        "signs": {},
        "context_disambiguation_rules": [],
        "compound_signs": [],
        "ngram_probabilities": {}
    }

    # Process each sign in Borger list + observed signs
    all_sign_ids = set(BORGER_SIGN_LIST.keys()) | observed_signs

    for sign_id in sorted(all_sign_ids):
        borger_info = BORGER_SIGN_LIST.get(sign_id, {})

        # Get readings from corpus (frequency-based)
        count = total_counts.get(sign_id, 0)
        freq_rank = sorted(total_counts.values(), reverse=True).index(count) + 1 if count > 0 else 999

        # Determine language-specific readings based on sign
        sumerian_readings = []
        akkadian_readings = []
        logographic_values = borger_info.get("logographic", [])

        # Add from Borger mapping
        if sign_id == "A":
            sumerian_readings = ["a", "á", "à", "a5", "a8"]
            akkadian_readings = ["a", "ea", "ā", "ya", "i"]
        elif sign_id == "AN":
            sumerian_readings = ["an", "an5", "an8"]
            akkadian_readings = ["ilu", "šamû", "amû"]
        elif sign_id == "DINGIR":
            sumerian_readings = ["an", "an5"]
            akkadian_readings = ["ilu"]
        elif sign_id == "EN":
            sumerian_readings = ["en", "en2"]
            akkadian_readings = ["bēlu", "belu"]
        elif sign_id == "KI":
            sumerian_readings = ["ki", "gi", "ge"]
            akkadian_readings = ["erṣetu", "qāqqaru"]
        elif sign_id == "LUGAL":
            sumerian_readings = ["lugal"]
            akkadian_readings = ["šarru"]
        elif sign_id == "NI":
            sumerian_readings = ["ni", "ni2", "ni3"]
            akkadian_readings = ["aššu"]
        elif sign_id == "URU":
            sumerian_readings = ["uru"]
            akkadian_readings = ["ālu"]
        elif sign_id == "MA":
            sumerian_readings = ["ma", "ma2"]
            akkadian_readings = ["aš", "aš2"]
        elif sign_id == "E2":
            sumerian_readings = ["e2", "é"]
            akkadian_readings = ["bītu"]
        elif sign_id in ["WEDGE", "VERTICAL", "HORIZONTAL", "ANGLED", "COMPLEX"]:
            # Detected sign types, not actual signs
            sumerian_readings = [sign_id.lower()]
            akkadian_readings = [sign_id.lower()]
        else:
            # Default: use sign as reading
            sumerian_readings = [sign_id.lower()]
            akkadian_readings = [sign_id.lower()]

        # Build context rules for this sign from corpus co-occurrence
        context_rules = []
        sign_contexts = context_probs.get(sign_id, {})

        # Add high-probability context rules from corpus
        for ctx_sign, prob in sorted(sign_contexts.items(), key=lambda x: x[1], reverse=True)[:10]:
            if prob > 0.01:  # Only significant co-occurrences
                context_rules.append({
                    "pattern": f"{sign_id}.{ctx_sign}" if sign_id < ctx_sign else f"{ctx_sign}.{sign_id}",
                    "reading": f"{sign_id.lower()}.{ctx_sign.lower()}",
                    "translation": f"{sign_id}-{ctx_sign} compound",
                    "pos": "X",
                    "corpus_probability": round(prob, 4),
                    "source": "corpus_trained"
                })

        # Add template rules that match this sign
        for template in CONTEXT_RULE_TEMPLATES:
            if sign_id in template.get("pattern", ""):
                context_rules.append({
                    "pattern": template["pattern"],
                    "reading": template.get("reading", ""),
                    "translation": template.get("description", ""),
                    "pos": template.get("pos", "X"),
                    "template_priority": template.get("priority", 50),
                    "source": "template"
                })

        # Add observed n-gram probabilities
        ngram_probs = {}
        for ctx_sign, prob in sorted(sign_contexts.items(), key=lambda x: x[1], reverse=True)[:20]:
            ngram_probs[f"{sign_id}→{ctx_sign}"] = round(prob, 6)

        sign_entry = {
            "unicode": borger_info.get("unicode", ""),
            "borger": borger_info.get("borger", ""),
            "name": borger_info.get("name", sign_id),
            "sumerian_readings": sumerian_readings,
            "akkadian_readings": akkadian_readings,
            "logographic_values": logographic_values,
            "context_rules": context_rules,
            "frequency_rank": freq_rank,
            "corpus_frequency": count,
            "periods": ["ED", "EDIII", "OLD_AKKADIAN", "URIII", "OB", "MB", "LB", "NA", "NB"] if count > 0 else [],
            "observed_in_corpus": count > 0
        }

        polyphony_catalog["signs"][sign_id] = sign_entry
        polyphony_catalog["ngram_probabilities"][sign_id] = ngram_probs

    # 6️⃣ Add context disambiguation rules
    polyphony_catalog["context_disambiguation_rules"] = CONTEXT_RULE_TEMPLATES

    # 7️⃣ Add compound signs
    polyphony_catalog["compound_signs"] = COMPOUND_SIGNS

    # 8️⃣ Save to JSON
    log.info(f"💾 Saving polyphony catalog to {POLYPHONY_OUTPUT}")
    with open(POLYPHONY_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(polyphony_catalog, f, indent=2, ensure_ascii=False)

    # 9️⃣ Print summary
    total_signs = len(polyphony_catalog["signs"])
    observed = sum(1 for s in polyphony_catalog["signs"].values() if s["observed_in_corpus"])
    total_rules = len(polyphony_catalog["context_disambiguation_rules"])
    total_compounds = len(polyphony_catalog["compound_signs"])

    log.info("=" * 70)
    log.info("✅ POLYPHONY TRAINING COMPLETE")
    log.info("=" * 70)
    log.info(f"  Total signs in catalog: {total_signs}")
    log.info(f"  Signs observed in corpus: {observed}")
    log.info(f"  Context disambiguation rules: {total_rules}")
    log.info(f"  Compound signs: {total_compounds}")
    log.info(f"  Output: {POLYPHONY_OUTPUT}")

    conn.close()
    return polyphony_catalog


if __name__ == "__main__":
    catalog = train_polyphony_from_corpus()
    print(f"\nTraining complete: {len(catalog['signs'])} signs, "
          f"{len(catalog['context_disambiguation_rules'])} rules, "
          f"{len(catalog['compound_signs'])} compounds")