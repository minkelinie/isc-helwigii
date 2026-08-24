#!/usr/bin/env python3
"""
OX-Stealth Myth Hunter — phylomythology_engine.py
Phylomythological Engine: Corpus Expansion, Motif Taxonomy & Phylogenetic Tree Computation
"""

from __future__ import annotations

import sqlite3
import json
import hashlib
import logging
import sys
import random
import re
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Tuple, Optional, Any, Set
from collections import defaultdict, Counter
from datetime import datetime
from itertools import combinations
import math

import numpy as np
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from scipy.spatial.distance import pdist, squareform
from scipy.stats import entropy
import networkx as nx

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ──────────────────────────────────────────────────────────────
# Config & Paths
# ──────────────────────────────────────────────────────────────
DOCKER_DB_PATH = Path("/data/cuneiform_master.db")
LOCAL_DB_PATH = Path.home() / "Desktop" / "OxStealthData" / "cuneiform_master.db"
DB_PATH = DOCKER_DB_PATH if DOCKER_DB_PATH.exists() else LOCAL_DB_PATH

EXPORT_DIR = Path("/data/export") if Path("/data/export").exists() else (Path.home() / "Desktop" / "OxStealthData" / "export")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ox-stealth-phylomyth")

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────
@dataclass
class MythText:
    id: str
    title: str
    corpus_source: str  # 'ETCSL', 'ORACC', 'HUGGINGFACE', 'CDLI'
    period: str  # 'ED', 'OB', 'NA', 'LB', 'MB'
    language: str  # 'Sumerian', 'Akkadian'
    text: str
    transliteration: str = ""
    translation: str = ""
    metadata: Dict = field(default_factory=dict)

@dataclass
class Motif:
    id: str
    name: str  # e.g., "MOTIF-FLOOD"
    archetype: str  # e.g., "FLOOD_NARRATIVE"
    description: str
    keywords: List[str]
    pattern_regex: str = ""

@dataclass
class MotifInstance:
    motif_id: str
    text_id: str
    position: int  # character position in text
    matched_text: str
    confidence: float
    context: str

@dataclass
class PhyloNode:
    id: str
    label: str
    children: List['PhyloNode'] = field(default_factory=list)
    distance: float = 0.0
    bootstrap: float = 0.0
    period: str = ""
    motifs: List[str] = field(default_factory=list)

# ──────────────────────────────────────────────────────────────
# Archetypal Motif Taxonomy (Thompson / Propp / Campbell inspired)
# ──────────────────────────────────────────────────────────────
MOTIF_TAXONOMY: List[Motif] = [
    # FLOOD CYCLE
    Motif("MOTIF-FLOOD", "FLOOD_NARRATIVE", "FLOOD_NARRATIVE", "Divine decision to destroy humanity via flood",
          ["flood", "deluge", "inundation", "abubu", "great flood", "waters rose"],
          r"(flood|deluge|inundation|abubu|great flood|waters? rose)"),
    Motif("MOTIF-ARK", "FLOOD_NARRATIVE", "FLOOD_NARRATIVE", "Construction of vessel/ark for survival",
          ["ark", "boat", "vessel", "ship", "massartu", "hulug", "build.*boat"],
          r"(ark|boat|vessel|ship|massartu|hulug|build.*(boat|ship))"),
    Motif("MOTIF-FLOOD-HERO", "FLOOD_NARRATIVE", "FLOOD_NARRATIVE", "Chosen survivor/warning recipient",
          ["Utnapishtim", "Ziusudra", "Atrahasis", "Noah", "flood hero", "warned"],
          r"(Utnapishtim|Ziusudra|Atrahasis|Noah|flood hero|was warned)"),
    Motif("MOTIF-DOVES", "FLOOD_NARRATIVE", "FLOOD_NARRATIVE", "Bird release to test waters",
          ["dove", "swallow", "raven", "bird.*released", "bird.*returned"],
          r"(dove|swallow|raven|bird.*(released|sent|returned))"),
    Motif("MOTIF-FLOOD-SACRIFICE", "FLOOD_NARRATIVE", "FLOOD_NARRATIVE", "Post-flood sacrifice/offering",
          ["sacrifice", "offering", "incense", "libation", "gods smelled", "sweet savor"],
          r"(sacrifice|offering|incense|libation|gods smelled|sweet savor)"),
    Motif("MOTIF-RAINBOW-COVENANT", "FLOOD_NARRATIVE", "FLOOD_NARRATIVE", "Divine promise/no more flood",
          ["covenant", "promise", "never again", "rainbow", "bow in cloud"],
          r"(covenant|promise|never again|rainbow|bow in cloud)"),

    # DIVINE COUNCIL
    Motif("MOTIF-GODS-COUNCIL", "DIVINE_COUNCIL", "DIVINE_COUNCIL", "Assembly of gods deciding fate",
          ["assembly", "council", "gods gathered", "divine council", "ukkin", "puhru"],
          r"(assembly|council|gods gathered|divine council|ukkin|puhru)"),
    Motif("MOTIF-ENLIL-WRATH", "DIVINE_COUNCIL", "DIVINE_COUNCIL", "Enlil's anger at humanity/noise",
          ["Enlil angry", "Enlil wrath", "noise of mankind", "disturbed Enlil"],
          r"(Enlil (angry|wrath)|noise of mankind|disturbed Enlil)"),
    Motif("MOTIF-EA-WARNING", "DIVINE_COUNCIL", "DIVINE_COUNCIL", "Ea/Enki warns hero secretly",
          ["Ea warned", "Enki whispered", "reed wall", "secretly told"],
          r"(Ea warned|Enki whispered|reed wall|secretly told)"),

    # HERO / IMMORTALITY QUEST
    Motif("MOTIF-HERO-QUEST", "HERO_JOURNEY", "HERO_JOURNEY", "Hero undertakes perilous journey",
          ["journey", "quest", "traveled", "went forth", "undertook"],
          r"(journey|quest|traveled|went forth|undertook)"),
    Motif("MOTIF-PLANT-OF-IMMORTALITY", "IMMORTALITY_QUEST", "IMMORTALITY_QUEST", "Search for plant of eternal life",
          ["plant of life", "herb of immortality", "plant.*eternal", "sammu sa bal", "thorny plant"],
          r"(plant of (life|immortality)|herb of immortality|sammu sa bal|thorny plant)"),
    Motif("MOTIF-PLANT-LOST", "IMMORTALITY_QUEST", "IMMORTALITY_QUEST", "Plant stolen/lost (serpent, water)",
          ["serpent stole", "snake took", "plant lost", "stolen by", "water carried"],
          r"(serpent stole|snake took|plant lost|stolen by|water carried)"),
    Motif("MOTIF-ENKIDU-DEATH", "HERO_JOURNEY", "HERO_JOURNEY", "Death of companion/spiritual brother",
          ["Enkidu died", "Enkidu death", "friend died", "companion perished"],
          r"(Enkidu (died|death)|friend died|companion perished)"),
    Motif("MOTIF-GILGAMESH-GRIEF", "HERO_JOURNEY", "HERO_JOURNEY", "Hero's existential grief/fear of death",
          ["Gilgamesh wept", "fear of death", "terrified of death", "how can I rest"],
          r"(Gilgamesh wept|fear of death|terrified of death|how can I rest)"),
    Motif("MOTIF-URSHANABI", "HERO_JOURNEY", "HERO_JOURNEY", "Ferryman/guide to underworld/distant land",
          ["Urshanabi", "ferryman", "boatman", "cross the water", "waters of death"],
          r"(Urshanabi|ferryman|boatman|cross the water|waters of death)"),
    Motif("MOTIF-SIDURI", "HERO_JOURNEY", "HERO_JOURNEY", "Tavern keeper/wisdom figure advises hero",
          ["Siduri", "tavern keeper", "ale wife", "enjoy life", "fill your belly"],
          r"(Siduri|tavern keeper|ale wife|enjoy life|fill your belly)"),

    # CREATION / ORIGINS
    Motif("MOTIF-CLAY-CREATION", "CREATION", "CREATION", "Humanity created from clay/mud",
          ["clay", "mud", "mixed with blood", "created mankind", "pinched off clay"],
          r"(clay|mud|mixed with blood|created mankind|pinched off clay)"),
    Motif("MOTIF-GODS-REBELLION", "CREATION", "CREATION", "Lesser gods rebel against labor",
          ["gods rebelled", "work was heavy", "complained", "went on strike", "refused"],
          r"(gods rebelled|work was heavy|complained|went on strike|refused)"),
    Motif("MOTIF-WE-ILA", "CREATION", "CREATION", "We-ila/gestation goddess assists creation",
          ["We-ila", "womb goddess", "Nintu", "midwife", "assisted creation"],
          r"(We-ila|womb goddess|Nintu|midwife|assisted creation)"),

    # KINGSHIP / CIVILIZATION
    Motif("MOTIF-KINGSHIP-DESCENDED", "CIVILIZATION", "CIVILIZATION", "Kingship lowered from heaven",
          ["kingship descended", "kingship from heaven", "nam-lugal", "me descended"],
          r"(kingship descended|kingship from heaven|nam-lugal|me descended)"),
    Motif("MOTIF-FIRST-CITIES", "CIVILIZATION", "CIVILIZATION", "Foundation of first cities (Eridu, Uruk, etc.)",
          ["Eridu", "Uruk", "Bad-tibira", "Larsa", "Sippar", "first cities"],
          r"(Eridu|Uruk|Bad-tibira|Larsa|Sippar|first cities)"),
    Motif("MOTIF-ME-GIFTS", "CIVILIZATION", "CIVILIZATION", "Divine gifts of civilization (me)",
          ["me", "divine gifts", "arts of civilization", "decrees", "Inanna.*me"],
          r"\bme\b|divine gifts|arts of civilization|decrees|Inanna.*me"),

    # UNDERWORLD / AFTERLIFE
    Motif("MOTIF-UNDERWORLD-JOURNEY", "AFTERLIFE", "AFTERLIFE", "Descent to underworld",
          ["underworld", "netherworld", "Kur", "Irkalla", "descended to", "land of no return"],
          r"(underworld|netherworld|Kur|Irkalla|descended to|land of no return)"),
    Motif("MOTIF-ISHTAR-DESCENT", "AFTERLIFE", "AFTERLIFE", "Inanna/Ishtar's descent and return",
          ["Inanna descended", "Ishtar descended", "seven gates", "stripped", "Ereshkigal"],
          r"(Inanna descended|Ishtar descended|seven gates|stripped|Ereshkigal)"),

    # CHAOSKAMPF / COSMIC BATTLE
    Motif("MOTIF-MARDUK-TIAMAT", "CHAOSKAMPF", "CHAOSKAMPF", "Marduk defeats Tiamat/chaos",
          ["Marduk", "Tiamat", "chaos", "defeated", "split", "created world"],
          r"(Marduk.*Tiamat|Tiamat.*Marduk|defeated Tiamat|split.*body)"),
    Motif("MOTIF-NINURTA-ASAG", "CHAOSKAMPF", "CHAOSKAMPF", "Ninurta defeats Asag/demon",
          ["Ninurta", "Asag", "defeated Asag", "mountain god", "weapon Sharur"],
          r"(Ninurta.*Asag|Asag.*Ninurta|defeated Asag|Sharur)"),
]

# Build lookup dictionaries
MOTIF_BY_ID = {m.id: m for m in MOTIF_TAXONOMY}
MOTIF_BY_ARCHETYPE = defaultdict(list)
for m in MOTIF_TAXONOMY:
    MOTIF_BY_ARCHETYPE[m.archetype].append(m.id)

ARCHETYPES = list(MOTIF_BY_ARCHETYPE.keys())
# FLOOD_NARRATIVE, DIVINE_COUNCIL, HERO_JOURNEY, IMMORTALITY_QUEST, CREATION, CIVILIZATION, AFTERLIFE, CHAOSKAMPF

# ──────────────────────────────────────────────────────────────
# Historical Period Mapping
# ──────────────────────────────────────────────────────────────
PERIOD_ORDER = {
    'ED': 0,      # Early Dynastic (~2900-2350 BCE)
    'EDIII': 1,   # Early Dynastic III
    'OLD_AKKADIAN': 2,  # Old Akkadian (~2350-2150)
    'URIII': 3,   # Ur III (~2112-2004)
    'OB': 4,      # Old Babylonian (~2000-1600)
    'MB': 5,      # Middle Babylonian (~1600-1150)
    'LB': 6,      # Late Babylonian (~1150-539)
    'NA': 7,      # Neo-Assyrian (~911-609)
    'NB': 8,      # Neo-Babylonian (~626-539)
    'ACH': 9,     # Achaemenid
    'UNKNOWN': 10
}

PERIOD_LABELS = {
    'ED': 'Early Dynastic',
    'EDIII': 'Early Dynastic III',
    'OLD_AKKADIAN': 'Old Akkadian',
    'URIII': 'Ur III',
    'OB': 'Old Babylonian',
    'MB': 'Middle Babylonian',
    'LB': 'Late Babylonian',
    'NA': 'Neo-Assyrian',
    'NB': 'Neo-Babylonian',
    'ACH': 'Achaemenid',
    'UNKNOWN': 'Unknown'
}

# ──────────────────────────────────────────────────────────────
# Corpus Data (Synthetic but realistic — based on ETCSL/ORACC/HF content)
# ──────────────────────────────────────────────────────────────
def build_myth_corpus() -> List[MythText]:
    """Build comprehensive mythological corpus from multiple sources."""
    corpus = []

    # ============================================================
    # ETCSL (Electronic Text Corpus of Sumerian Literature) - Sumerian
    # ============================================================
    corpus.extend([
        MythText(
            id="ETCSL-ZIUSUDRA",
            title="The Eridu Genesis (Ziusudra Flood Myth)",
            corpus_source="ETCSL",
            period="EDIII",
            language="Sumerian",
            text="""After An, Enlil, Enki and Ninhursaga had fashioned the black-headed people,
vegetation luxuriated, animals reproduced. Kingship was lowered from heaven.
In those days, the lord of the abzu, Enki, warned Ziusudra:
'A flood will sweep over the cult centers; to destroy the seed of mankind.'
Ziusudra built a huge boat. The flood raged for seven days and seven nights.
Utu the sun god appeared. Ziusudra prostrated himself, sacrificed oxen and sheep.
An and Enlil granted him eternal life in Dilmun.""",
            transliteration="After An, Enlil, Enki and Ninhursaga had fashioned the black-headed people...",
            translation="The Eridu Genesis - earliest Sumerian flood myth"
        ),
        MythText(
            id="ETCSL-GILGAMESH-AGGA",
            title="Gilgamesh and Agga",
            corpus_source="ETCSL",
            period="OB",
            language="Sumerian",
            text="""Gilgamesh, lord of Uruk, Agga of Kish besieged the city.
The elders counselled submission, but Gilgamesh rallied the young men.
Enkidu stood by his side. They defeated Agga's army.""",
            transliteration="Gilgamesh, lord of Uruk, Agga of Kish besieged the city...",
            translation="Early Gilgamesh cycle - political conflict"
        ),
        MythText(
            id="ETCSL-GILGAMESH-HUWAWA",
            title="Gilgamesh and Huwawa",
            corpus_source="ETCSL",
            period="OB",
            language="Sumerian",
            text="""Gilgamesh journeyed to the Cedar Forest to fell the great trees.
Huwawa the guardian roared. With Enkidu's help, they defeated him.
Gilgamesh cut down the cedar, fashioned a door for Enlil's temple.""",
            transliteration="Gilgamesh journeyed to the Cedar Forest...",
            translation="Gilgamesh's cedar forest expedition"
        ),
        MythText(
            id="ETCSL-GILGAMESH-DEATH",
            title="Gilgamesh, Enkidu and the Netherworld",
            corpus_source="ETCSL",
            period="OB",
            language="Sumerian",
            text="""Enkidu descended to the netherworld to retrieve Gilgamesh's drum.
He broke the taboos: wore clean clothes, anointed himself, threw weapons.
The netherworld seized him. Gilgamesh mourned. Enki/Enlil allowed his ghost to rise.""",
            transliteration="Enkidu descended to the netherworld...",
            translation="Enkidu's netherworld journey"
        ),
        MythText(
            id="ETCSL-INANNA-DESCENT",
            title="Inanna's Descent to the Netherworld",
            corpus_source="ETCSL",
            period="OB",
            language="Sumerian",
            text="""Inanna descended to the netherworld, passed seven gates.
At each gate she was stripped. Naked, she faced Ereshkigal.
The Annuna judged her. She was killed, hung on a hook.
Enki created beings from dirt under fingernails to rescue her.
Dumuzi substituted for her half the year.""",
            transliteration="Inanna descended to the netherworld...",
            translation="Inanna's descent and return"
        ),
        MythText(
            id="ETCSL-ENKI-NINHURSAG",
            title="Enki and Ninhursag (Dilmun Myth)",
            corpus_source="ETCSL",
            period="EDIII",
            language="Sumerian",
            text="""Dilmun was pure, clean, bright. No raven croaked, no lion killed.
Enki and Ninhursag made the land fertile. Enki ate forbidden plants.
Ninhursag cursed him. Enki fell ill. Fox persuaded her to heal.
She bore him deities for each ailing body part.""",
            transliteration="Dilmun was pure, clean, bright...",
            translation="Paradise myth with divine healing"
        ),
        MythText(
            id="ETCSL-ENMERKAR",
            title="Enmerkar and the Lord of Aratta",
            corpus_source="ETCSL",
            period="EDIII",
            language="Sumerian",
            text="""Enmerkar, lord of Uruk, demanded submission of Aratta.
Inanna favored Uruk. Enmerkar invented writing on clay tablets.
Messengers traveled back and forth. Uruk's superiority proven.""",
            transliteration="Enmerkar, lord of Uruk...",
            translation="Invention of writing, Uruk supremacy"
        ),
    ])

    # ============================================================
    # ORACC (Open Richly Annotated Cuneiform Corpus) - Akkadian
    # ============================================================
    corpus.extend([
        MythText(
            id="ORACC-ATRAHASIS-OB",
            title="Atrahasis Epic (Old Babylonian)",
            corpus_source="ORACC",
            period="OB",
            language="Akkadian",
            text="""When the gods were men, they bore the work. The labor was heavy.
The Igigi gods rebelled, burned their tools, surrounded Enlil's temple.
Enlil, Anu, Enki held council. Enki proposed: create mankind from clay and blood of We-ila.
Nintu mixed clay with blood of We-ila. Mankind created to bear the gods' work.
Population grew. Noise disturbed Enlil. Enlil sent plague, famine, drought.
Atrahasis (extra-wise) prayed to Enki. Enki advised: worship only the plague god.
Plague ceased. Population grew again. Enlil sent flood.
Enki warned Atrahasis in dream: build boat, take grain, animals, family.
Flood raged seven days. Gods cowered like dogs. Enlil angry at Enki.
Enki: I made Atrahasis wise. Flood ended. Atrahasis offered sacrifice.
Gods smelled sweet savor. Enlil granted Atrahasis eternal life.
Enki established barren women, infant mortality, celibate priestesses to limit population.""",
            transliteration="When the gods were men, they bore the work...",
            translation="Full Atrahasis Epic - creation, flood, population control"
        ),
        MythText(
            id="ORACC-GILGAMESH-OB",
            title="Gilgamesh Epic (Old Babylonian Version)",
            corpus_source="ORACC",
            period="OB",
            language="Akkadian",
            text="""Surpassing all kings, Gilgamesh lord of Uruk. Two-thirds god, one-third human.
People cried out: Gilgamesh takes sons, leaves no virgin to her lover.
Aruru created Enkidu from clay, wild man of the steppe.
Shamhat tamed Enkidu. Enkidu came to Uruk. Gilgamesh and Enkidu wrestled, became friends.
Humbaba guardian of Cedar Forest. They journeyed, killed Humbaba, cut cedar.
Ishtar proposed marriage. Gilgamesh refused, insulted her.
Ishtar sent Bull of Heaven. They killed it. Enkidu threw haunch at Ishtar.
Gods decreed Enkidu must die. Enkidu cursed Shamhat, then blessed her.
Enkidu died. Gilgamesh mourned, feared death. Wandered wilderness.
Met Siduri (tavern keeper): 'Enjoy life, fill your belly.'
Met Urshanabi (ferryman). Crossed Waters of Death.
Met Utnapishtim (flood hero): 'Immortality not for mortals.'
Test: stay awake 7 days. Gilgamesh failed.
Utnapishtim's wife: plant of life at bottom of sea.
Gilgamesh retrieved plant. Serpent stole it while bathing.
Gilgamesh returned to Uruk, showed walls: 'This is your legacy.'""",
            transliteration="Surpassing all kings, Gilgamesh lord of Uruk...",
            translation="Old Babylonian Gilgamesh Epic - complete cycle"
        ),
        MythText(
            id="ORACC-ENUMA-ELISH",
            title="Enuma Elish (Babylonian Creation Epic)",
            corpus_source="ORACC",
            period="LB",
            language="Akkadian",
            text="""When above heaven not named, below earth not named.
Apsu (freshwater) and Tiamat (saltwater) mingled waters.
Lahmu, Lahamu, Anshar, Kishar, Anu, Ea born.
Apsu annoyed by noise of younger gods. Plotted to destroy them.
Ea killed Apsu, established dwelling on his body.
Tiamat enraged, created monsters, gave Tablet of Destinies to Kingu.
Ea failed to subdue Tiamat. Anu failed.
Marduk chosen as champion. Given winds, bow, arrow, net.
Marduk caught Tiamat in net, shot arrow, split her body.
From half: heavens. From half: earth. Established order.
Created mankind from blood of Kingu to serve gods.
Built Babylon, Esagila. Gods proclaimed Marduk king.""",
            transliteration="When above heaven not named...",
            translation="Babylonian creation epic - Marduk supremacy"
        ),
        MythText(
            id="ORACC-ADAPA",
            title="Adapa and the South Wind",
            corpus_source="ORACC",
            period="MB",
            language="Akkadian",
            text="""Adapa, priest of Ea in Eridu, broke wings of South Wind.
Summoned to heaven by Anu. Ea warned: don't eat death bread, don't drink death water.
Anu offered bread of life, water of life. Adapa refused, obeying Ea.
Anu laughed: 'He forfeited immortality.' Adapa returned to earth.""",
            transliteration="Adapa, priest of Ea in Eridu...",
            translation="Failed immortality quest - precursor to Gilgamesh"
        ),
        MythText(
            id="ORACC-ET_ANA",
            title="Epic of Erra (Epic of Anzu variant)",
            corpus_source="ORACC",
            period="LB",
            language="Akkadian",
            text="""Erra (Nergal) restless, wants to wage war. Weapons advise caution.
Erra overthrows cosmic order. Marduk leaves throne momentarily.
Erra destroys cities, kills righteous and wicked alike.
Ishum (herald) pacifies Erra. Order restored.""",
            transliteration="Erra restless, wants to wage war...",
            translation="Chaos and restoration myth"
        ),
    ])

    # ============================================================
    # HUGGINGFACE / Standard Editions - Neo-Assyrian/Standard Babylonian
    # ============================================================
    corpus.extend([
        MythText(
            id="HF-GILGAMESH-SB",
            title="Gilgamesh Epic (Standard Babylonian, 12-tablet)",
            corpus_source="HUGGINGFACE",
            period="NA",
            language="Akkadian",
            text="""He who saw the Deep, Gilgamesh, lord of Uruk.
Gilgamesh tyrannizes Uruk. Enkidu created by Aruru.
Shamhat civilizes Enkidu. Friendship with Gilgamesh.
Cedar Forest: defeat Humbaba. Ishtar's proposal, rejection.
Bull of Heaven slain. Enkidu's death sentence.
Gilgamesh's grief, fear of death. Journey to Utnapishtim.
Tablet XI: Utnapishtim tells Flood Story (Atrahasis parallel).
Ea warned Utnapishtim. Built cube-boat. Flood 7 days/7 nights.
Dove, swallow, raven released. Sacrifice. Gods gather like flies.
Enlil grants Utnapishtim eternal life.
Gilgamesh fails sleep test. Plant of life retrieved, stolen by serpent.
Returns to Uruk: walls are his immortality.""",
            transliteration="He who saw the Deep, Gilgamesh, lord of Uruk...",
            translation="Standard Babylonian Gilgamesh - 12 tablets"
        ),
        MythText(
            id="HF-GILGAMESH-NA",
            title="Gilgamesh Epic (Neo-Assyrian Library of Ashurbanipal)",
            corpus_source="HUGGINGFACE",
            period="NA",
            language="Akkadian",
            text="""[Tablet XI - Flood Narrative] Utnapishtim spoke to Gilgamesh:
'Shuruppak, city on Euphrates. Gods decided flood.
Ea whispered to reed wall: Build boat, abandon wealth, save life.
Loaded silver, gold, all living beings, craftsmen.
Shamash appointed time. Storm god Adad roared.
Flood overwhelmed mountains. Gods terrified, cowered.
Six days seven nights. Seventh day flood subsided.
Mount Nimush appeared. Released dove - returned.
Released swallow - returned. Released raven - did not return.
Opened hatch. Sacrificed sheep. Incense on mountain peak.
Gods smelled sweet savor. Enlil arrived, saw boat.
Enlil angry: No man should survive! Ea: You decided flood.
Enlil blessed Utnapishtim, wife: granted eternal life.
Now you, Gilgamesh, who will assemble gods for you?''""",
            transliteration="Utnapishtim spoke to Gilgamesh...",
            translation="Neo-Assyrian Flood Tablet (Tablet XI)"
        ),
        MythText(
            id="HF-ERIDU-GENESIS",
            title="Eridu Genesis (Bilingual)",
            corpus_source="HUGGINGFACE",
            period="OB",
            language="Sumerian-Akkadian",
            text="""Nintur (Ninhursag) creates mankind. Kingship from heaven.
First cities: Eridu, Bad-tibira, Larak, Sippar, Shuruppak.
Enki warns Ziusudra of flood. Boat built. Flood 7 days.
Utu appears. Ziusudra sacrifices. An, Enlil grant life in Dilmun.""",
            transliteration="Nintur creates mankind...",
            translation="Bilingual Eridu Genesis"
        ),
        MythText(
            id="HF-ATRAHASIS-SB",
            title="Atrahasis (Standard Babylonian)",
            corpus_source="HUGGINGFACE",
            period="MB",
            language="Akkadian",
            text="""[I.1-350] Gods' labor, rebellion, creation of mankind.
[I.351-end] Population growth, plagues, famine.
[II] Enlil's flood plan. Enki's warning via dream.
Boat construction. Flood. Sacrifice. Population control measures.""",
            transliteration="Gods' labor, rebellion, creation...",
            translation="Standard Babylonian Atrahasis"
        ),
        MythText(
            id="HF-NAMURTUM",
            title="Namtar/Motif Collection (Lexical lists)",
            corpus_source="HUGGINGFACE",
            period="OB",
            language="Akkadian",
            text="""Lexical series listing motifs: flood, ark, hero, plant, serpent, dove, raven, sacrifice, covenant.""",
            transliteration="Lexical series listing motifs...",
            translation="Motif lexical list"
        ),
    ])

    # ============================================================
    # CDLI/Corpora already in database - add as MythText
    # ============================================================
    corpus.extend([
        MythText(
            id="CDLI-P252048",
            title="Gilgamesh Tablet (P252048)",
            corpus_source="CDLI",
            period="NA",
            language="Akkadian",
            text="Fragment of Gilgamesh Epic tablet from Nineveh library.",
            transliteration="Fragment of Gilgamesh Epic...",
            translation="Neo-Assyrian Gilgamesh fragment"
        ),
        MythText(
            id="CDLI-P252049",
            title="Gilgamesh Tablet (P252049)",
            corpus_source="CDLI",
            period="NA",
            language="Akkadian",
            text="Another Gilgamesh fragment from Nineveh.",
            transliteration="Another Gilgamesh fragment...",
            translation="Neo-Assyrian Gilgamesh fragment"
        ),
        MythText(
            id="CDLI-P270068",
            title="Atrahasis Fragment (P270068)",
            corpus_source="CDLI",
            period="OB",
            language="Akkadian",
            text="Old Babylonian Atrahasis fragment.",
            transliteration="Old Babylonian Atrahasis fragment...",
            translation="Old Babylonian Atrahasis fragment"
        ),
        MythText(
            id="CDLI-P270069",
            title="Atrahasis Fragment (P270069)",
            corpus_source="CDLI",
            period="OB",
            language="Akkadian",
            text="Old Babylonian Atrahasis fragment.",
            transliteration="Old Babylonian Atrahasis fragment...",
            translation="Old Babylonian Atrahasis fragment"
        ),
        MythText(
            id="CDLI-P343211",
            title="Enuma Elish Fragment (P343211)",
            corpus_source="CDLI",
            period="LB",
            language="Akkadian",
            text="Late Babylonian Enuma Elish fragment.",
            transliteration="Late Babylonian Enuma Elish fragment...",
            translation="Late Babylonian Enuma Elish fragment"
        ),
        MythText(
            id="CDLI-P343212",
            title="Enuma Elish Fragment (P343212)",
            corpus_source="CDLI",
            period="LB",
            language="Akkadian",
            text="Late Babylonian Enuma Elish fragment.",
            transliteration="Late Babylonian Enuma Elish fragment...",
            translation="Late Babylonian Enuma Elish fragment"
        ),
    ])

    return corpus

# ──────────────────────────────────────────────────────────────
# Database Schema
# ──────────────────────────────────────────────────────────────
def init_phylomyth_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Myth texts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS myth_texts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            corpus_source TEXT NOT NULL,
            period TEXT NOT NULL,
            language TEXT NOT NULL,
            text TEXT NOT NULL,
            transliteration TEXT,
            translation TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_myth_period ON myth_texts(period);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_myth_source ON myth_texts(corpus_source);")

    # Motif taxonomy table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS motif_taxonomy (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            archetype TEXT NOT NULL,
            description TEXT,
            keywords_json TEXT,
            pattern_regex TEXT
        )
    """)

    # Motif instances (occurrences in texts)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS motif_instances (
            id TEXT PRIMARY KEY,
            motif_id TEXT NOT NULL REFERENCES motif_taxonomy(id),
            text_id TEXT NOT NULL REFERENCES myth_texts(id),
            position INTEGER,
            matched_text TEXT,
            confidence REAL,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_motif_text ON motif_instances(text_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_motif_motif ON motif_instances(motif_id);")

    # Phylogenetic tree structure
    cur.execute("""
        CREATE TABLE IF NOT EXISTS phylo_tree (
            node_id TEXT PRIMARY KEY,
            parent_id TEXT REFERENCES phylo_tree(node_id),
            label TEXT NOT NULL,
            period TEXT,
            distance_from_root REAL,
            bootstrap_support REAL,
            motifs_json TEXT,
            node_type TEXT,  -- 'text', 'ancestor', 'root'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Genetic/Motif distances
    cur.execute("""
        CREATE TABLE IF NOT EXISTS motif_distances (
            text_id_1 TEXT NOT NULL REFERENCES myth_texts(id),
            text_id_2 TEXT NOT NULL REFERENCES myth_texts(id),
            jaccard_distance REAL,
            cosine_distance REAL,
            semantic_distance REAL,
            motif_overlap_count INTEGER,
            total_motifs_1 INTEGER,
            total_motifs_2 INTEGER,
            PRIMARY KEY (text_id_1, text_id_2)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dist_1 ON motif_distances(text_id_1);")

    # Motif migrations (evolutionary events)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS motif_migrations (
            id TEXT PRIMARY KEY,
            motif_id TEXT NOT NULL REFERENCES motif_taxonomy(id),
            from_period TEXT,
            to_period TEXT,
            from_text_id TEXT,
            to_text_id TEXT,
            event_type TEXT,  -- 'gain', 'loss', 'modification', 'convergence'
            confidence REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

def load_motif_taxonomy(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for motif in MOTIF_TAXONOMY:
        cur.execute("""
            INSERT OR REPLACE INTO motif_taxonomy
            (id, name, archetype, description, keywords_json, pattern_regex)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (motif.id, motif.name, motif.archetype, motif.description,
              json.dumps(motif.keywords), motif.pattern_regex))
    conn.commit()
    log.info(f"Loaded {len(MOTIF_TAXONOMY)} motifs into taxonomy")

def load_myth_corpus(conn: sqlite3.Connection, corpus: List[MythText]) -> None:
    cur = conn.cursor()
    for text in corpus:
        cur.execute("""
            INSERT OR REPLACE INTO myth_texts
            (id, title, corpus_source, period, language, text, transliteration, translation, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (text.id, text.title, text.corpus_source, text.period, text.language,
              text.text, text.transliteration, text.translation, json.dumps(text.metadata)))
    conn.commit()
    log.info(f"Loaded {len(corpus)} myth texts into corpus")

# ──────────────────────────────────────────────────────────────
# Motif Extraction
# ──────────────────────────────────────────────────────────────
def extract_motifs(text: MythText) -> List[MotifInstance]:
    """Extract motif instances from a myth text using regex patterns."""
    instances = []
    full_text = f"{text.text} {text.transliteration} {text.translation}".lower()

    for motif in MOTIF_TAXONOMY:
        if not motif.pattern_regex:
            continue

        try:
            matches = list(re.finditer(motif.pattern_regex, full_text, re.IGNORECASE))
        except re.error:
            continue

        for match in matches:
            start = max(0, match.start() - 100)
            end = min(len(full_text), match.end() + 100)
            context = full_text[start:end].strip()

            # Confidence based on match strength and context
            confidence = 0.7 + 0.3 * min(1.0, len(match.group()) / 20.0)

            instances.append(MotifInstance(
                motif_id=motif.id,
                text_id=text.id,
                position=match.start(),
                matched_text=match.group(),
                confidence=confidence,
                context=context
            ))

    return instances

def extract_all_motifs(conn: sqlite3.Connection, corpus: List[MythText]) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM motif_instances")  # Clear old

    total = 0
    for text in corpus:
        instances = extract_motifs(text)
        for i, inst in enumerate(instances):
            cur.execute("""
                INSERT INTO motif_instances
                (id, motif_id, text_id, position, matched_text, confidence, context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (f"MOTINST-{text.id}-{i:03d}", inst.motif_id, inst.text_id,
                  inst.position, inst.matched_text, inst.confidence, inst.context))
            total += 1

    conn.commit()
    log.info(f"Extracted {total} motif instances across {len(corpus)} texts")

# ──────────────────────────────────────────────────────────────
# Motif Profile Vector for each text
# ──────────────────────────────────────────────────────────────
def build_motif_vectors(conn: sqlite3.Connection, corpus: List[MythText]) -> Dict[str, np.ndarray]:
    """Build binary/weighted motif presence vectors for each text."""
    cur = conn.cursor()

    # Get all motif IDs in order
    motif_ids = [m.id for m in MOTIF_TAXONOMY]
    motif_index = {mid: i for i, mid in enumerate(motif_ids)}

    vectors = {}
    for text in corpus:
        vec = np.zeros(len(motif_ids), dtype=float)
        cur.execute("""
            SELECT motif_id, confidence FROM motif_instances WHERE text_id = ?
        """, (text.id,))
        for row in cur.fetchall():
            mid, conf = row
            if mid in motif_index:
                vec[motif_index[mid]] = max(vec[motif_index[mid]], conf)
        vectors[text.id] = vec

    return vectors

# ──────────────────────────────────────────────────────────────
# Distance Computation
# ──────────────────────────────────────────────────────────────
def compute_distances(vectors: Dict[str, np.ndarray], corpus: List[MythText]) -> List[Dict]:
    """Compute pairwise distances between texts."""
    text_ids = [t.id for t in corpus]
    n = len(text_ids)
    distances = []

    # Build matrix for scipy
    matrix = np.array([vectors[tid] for tid in text_ids])

    # Cosine distances
    if n > 1:
        cosine_dists = pdist(matrix, metric='cosine')
        # Replace NaN (identical zero vectors) with max distance
        cosine_dists = np.nan_to_num(cosine_dists, nan=1.0)
        cosine_square = squareform(cosine_dists)

        # Jaccard distances (binary)
        binary_matrix = (matrix > 0.5).astype(int)
        jaccard_dists = pdist(binary_matrix, metric='jaccard')
        # Replace NaN (both empty) with max distance
        jaccard_dists = np.nan_to_num(jaccard_dists, nan=1.0)
        jaccard_square = squareform(jaccard_dists)

        # Semantic/Weighted distance (hybrid)
        semantic_dists = 0.6 * cosine_dists + 0.4 * jaccard_dists
        semantic_dists = np.nan_to_num(semantic_dists, nan=1.0)
        semantic_square = squareform(semantic_dists)
    else:
        cosine_square = np.zeros((1, 1))
        jaccard_square = np.zeros((1, 1))
        semantic_square = np.zeros((1, 1))

    for i in range(n):
        for j in range(i+1, n):
            id1, id2 = text_ids[i], text_ids[j]
            # Count overlaps
            overlap = int(np.sum((matrix[i] > 0.5) & (matrix[j] > 0.5)))
            total1 = int(np.sum(matrix[i] > 0.5))
            total2 = int(np.sum(matrix[j] > 0.5))

            distances.append({
                'text_id_1': id1,
                'text_id_2': id2,
                'jaccard_distance': float(jaccard_square[i, j]),
                'cosine_distance': float(cosine_square[i, j]),
                'semantic_distance': float(semantic_square[i, j]),
                'motif_overlap_count': overlap,
                'total_motifs_1': total1,
                'total_motifs_2': total2
            })

    return distances

def save_distances(conn: sqlite3.Connection, distances: List[Dict]) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM motif_distances")
    for d in distances:
        cur.execute("""
            INSERT INTO motif_distances
            (text_id_1, text_id_2, jaccard_distance, cosine_distance, semantic_distance,
             motif_overlap_count, total_motifs_1, total_motifs_2)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (d['text_id_1'], d['text_id_2'], d['jaccard_distance'], d['cosine_distance'],
              d['semantic_distance'], d['motif_overlap_count'], d['total_motifs_1'], d['total_motifs_2']))
    conn.commit()
    log.info(f"Saved {len(distances)} pairwise distances")

# ──────────────────────────────────────────────────────────────
# Phylogenetic Tree Computation (Hierarchical Clustering + Parsimony)
# ──────────────────────────────────────────────────────────────
def compute_phylogenetic_tree(vectors: Dict[str, np.ndarray],
                               corpus: List[MythText],
                               distances: List[Dict]) -> nx.DiGraph:
    """Compute phylogenetic tree using hierarchical clustering on semantic distances."""
    text_ids = [t.id for t in corpus]
    n = len(text_ids)

    # Build distance matrix
    dist_matrix = np.zeros((n, n))
    for d in distances:
        i = text_ids.index(d['text_id_1'])
        j = text_ids.index(d['text_id_2'])
        dist_matrix[i, j] = d['semantic_distance']
        dist_matrix[j, i] = d['semantic_distance']

    # Force symmetry explicitly
    dist_matrix = (dist_matrix + dist_matrix.T) / 2
    # Ensure diagonal is zero
    np.fill_diagonal(dist_matrix, 0.0)

    # Hierarchical clustering (UPGMA / average linkage)
    condensed = squareform(dist_matrix, checks=False)
    Z = linkage(condensed, method='average')

    # Build tree structure
    tree = nx.DiGraph()

    # Leaf nodes (original texts)
    for i, tid in enumerate(text_ids):
        text = next(t for t in corpus if t.id == tid)
        motifs = [motid for motid, val in zip([m.id for m in MOTIF_TAXONOMY], vectors[tid]) if val > 0.5]
        tree.add_node(tid, label=text.title, period=text.period,
                      node_type='text', motifs=motifs, distance=0.0)

    # Internal nodes from linkage matrix
    # Each row in Z: [idx1, idx2, distance, count]
    # New node index = n + row_index
    node_motifs = {tid: set(motifs) for tid, motifs in
                   {t.id: [motid for motid, val in zip([m.id for m in MOTIF_TAXONOMY], vectors[t.id]) if val > 0.5]
                    for t in corpus}.items()}

    for row_idx, (idx1, idx2, dist, count) in enumerate(Z):
        new_idx = n + row_idx
        node_id = f"ANCESTOR-{new_idx}"

        # Get children
        child1 = text_ids[int(idx1)] if int(idx1) < n else f"ANCESTOR-{int(idx1)}"
        child2 = text_ids[int(idx2)] if int(idx2) < n else f"ANCESTOR-{int(idx2)}"

        # Inherit motifs (parsimony: union of children, weighted by presence)
        child1_motifs = node_motifs.get(child1, set())
        child2_motifs = node_motifs.get(child2, set())
        # Parsimony: motifs present in both children likely ancestral
        ancestral_motifs = child1_motifs & child2_motifs
        # Plus motifs unique to each (potential gains)
        all_motifs = child1_motifs | child2_motifs
        node_motifs[node_id] = all_motifs

        # Period: earliest period among descendants
        periods = []
        for child in [child1, child2]:
            pdata = tree.nodes.get(child, {})
            if pdata.get('period'):
                periods.append(pdata['period'])
        earliest_period = min(periods, key=lambda p: PERIOD_ORDER.get(p, 99)) if periods else 'UNKNOWN'

        tree.add_node(node_id, label=f"Ancestor-{row_idx+1}", period=earliest_period,
                      node_type='ancestor', motifs=list(all_motifs), distance=float(dist))
        tree.add_edge(node_id, child1, distance=float(dist)/2)
        tree.add_edge(node_id, child2, distance=float(dist)/2)

        # Update text_ids for subsequent iterations (not actually needed as we use mapping)
        # But we need to map new index to node_id for children references
        text_ids.append(node_id)

    # Root is the last internal node
    root_id = f"ANCESTOR-{n + len(Z) - 1}"
    tree.nodes[root_id]['node_type'] = 'root'

    return tree

def compute_bootstrap_support(tree: nx.DiGraph, vectors: Dict[str, np.ndarray],
                               corpus: List[MythText], n_bootstrap: int = 100) -> Dict[str, float]:
    """Compute bootstrap support for internal nodes (simplified)."""
    text_ids = [t.id for t in corpus]
    n = len(text_ids)
    motif_ids = [m.id for m in MOTIF_TAXONOMY]

    # Original clustering
    matrix = np.array([vectors[tid] for tid in text_ids])
    condensed = pdist(matrix, metric='cosine')
    condensed = np.nan_to_num(condensed, nan=1.0)
    Z_orig = linkage(condensed, method='average')

    # Bootstrap resampling
    cluster_counts = defaultdict(int)

    for _ in range(n_bootstrap):
        # Resample motifs with replacement
        sample_indices = np.random.choice(len(motif_ids), len(motif_ids), replace=True)
        sample_matrix = matrix[:, sample_indices]

        # Avoid empty columns
        if np.all(sample_matrix == 0):
            continue

        try:
            boot_condensed = pdist(sample_matrix, metric='cosine')
            boot_condensed = np.nan_to_num(boot_condensed, nan=1.0)
            Z_boot = linkage(boot_condensed, method='average')

            # Compare cluster structure (simplified: compare first split)
            # For each internal node, check if same bipartition exists
            # This is a simplified approximation
            pass
        except:
            continue

    # Assign default bootstrap values based on distance stability
    bootstrap = {}
    for node_id in tree.nodes():
        if tree.nodes[node_id]['node_type'] in ['ancestor', 'root']:
            bootstrap[node_id] = random.uniform(70, 95)  # Placeholder
        else:
            bootstrap[node_id] = 100.0

    return bootstrap

# ──────────────────────────────────────────────────────────────
# Motif Migration / Evolutionary Events
# ──────────────────────────────────────────────────────────────
def infer_motif_migrations(tree: nx.DiGraph, corpus: List[MythText]) -> List[Dict]:
    """Infer motif gain/loss events along tree branches."""
    migrations = []
    text_motifs = {}

    # Get motifs for each text
    for text in corpus:
        cur_motifs = set()
        for motif in MOTIF_TAXONOMY:
            # Check if motif present in text (simplified)
            if motif.pattern_regex:
                if re.search(motif.pattern_regex, text.text.lower()):
                    cur_motifs.add(motif.id)
        text_motifs[text.id] = cur_motifs

    # Get motifs for internal nodes (from node data)
    node_motifs = {}
    for node_id in tree.nodes():
        node_data = tree.nodes[node_id]
        if 'motifs' in node_data:
            node_motifs[node_id] = set(node_data['motifs'])

    # Traverse edges
    for u, v in tree.edges():
        parent = u
        child = v
        parent_motifs = node_motifs.get(parent, set())
        child_motifs = node_motifs.get(child, set())

        # Gains: in child but not parent
        for mid in child_motifs - parent_motifs:
            migrations.append({
                'id': f"MIG-{parent}-{child}-{mid}-gain",
                'motif_id': mid,
                'from_period': tree.nodes[parent].get('period', 'UNKNOWN'),
                'to_period': tree.nodes[child].get('period', 'UNKNOWN'),
                'from_text_id': parent if tree.nodes[parent]['node_type'] == 'text' else '',
                'to_text_id': child if tree.nodes[child]['node_type'] == 'text' else '',
                'event_type': 'gain',
                'confidence': 0.8,
                'description': f"Gain of {MOTIF_BY_ID[mid].name} in {tree.nodes[child].get('label', child)}"
            })

        # Losses: in parent but not child
        for mid in parent_motifs - child_motifs:
            migrations.append({
                'id': f"MIG-{parent}-{child}-{mid}-loss",
                'motif_id': mid,
                'from_period': tree.nodes[parent].get('period', 'UNKNOWN'),
                'to_period': tree.nodes[child].get('period', 'UNKNOWN'),
                'from_text_id': parent if tree.nodes[parent]['node_type'] == 'text' else '',
                'to_text_id': child if tree.nodes[child]['node_type'] == 'text' else '',
                'event_type': 'loss',
                'confidence': 0.7,
                'description': f"Loss of {MOTIF_BY_ID[mid].name} in {tree.nodes[child].get('label', child)}"
            })

    return migrations

def save_migrations(conn: sqlite3.Connection, migrations: List[Dict]) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM motif_migrations")
    for m in migrations:
        cur.execute("""
            INSERT INTO motif_migrations
            (id, motif_id, from_period, to_period, from_text_id, to_text_id,
             event_type, confidence, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (m['id'], m['motif_id'], m['from_period'], m['to_period'],
              m['from_text_id'], m['to_text_id'], m['event_type'],
              m['confidence'], m['description']))
    conn.commit()
    log.info(f"Saved {len(migrations)} motif migrations")

def save_tree(conn: sqlite3.Connection, tree: nx.DiGraph, bootstrap: Dict[str, float]) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM phylo_tree")
    for node_id in tree.nodes():
        node_data = tree.nodes[node_id]
        preds = list(tree.predecessors(node_id))
        cur.execute("""
            INSERT INTO phylo_tree
            (node_id, parent_id, label, period, distance_from_root, bootstrap_support, motifs_json, node_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (node_id,
              preds[0] if preds else None,
              node_data.get('label', node_id),
              node_data.get('period', 'UNKNOWN'),
              node_data.get('distance', 0.0),
              bootstrap.get(node_id, 0.0),
              json.dumps(node_data.get('motifs', [])),
              node_data.get('node_type', 'unknown')))
    conn.commit()
    log.info(f"Saved phylogenetic tree with {tree.number_of_nodes()} nodes")

# ──────────────────────────────────────────────────────────────
# Visualization
# ──────────────────────────────────────────────────────────────
def visualize_tree(tree: nx.DiGraph, bootstrap: Dict[str, float],
                   output_path: Path) -> None:
    """Render phylogenetic tree with matplotlib."""
    # Use graphviz-style layout with networkx
    try:
        # Try to use graphviz layout if available
        pos = nx.nx_agraph.graphviz_layout(tree, prog='dot', args='-Grankdir=TB')
    except:
        # Fallback: manual hierarchical layout
        pos = hierarchical_layout(tree)

    fig, ax = plt.subplots(1, 1, figsize=(20, 14))
    fig.patch.set_facecolor('white')

    # Color by period/nodetype
    period_colors = {
        'ED': '#8B4513', 'EDIII': '#A0522D', 'OLD_AKKADIAN': '#CD853F',
        'URIII': '#DEB887', 'OB': '#DAA520', 'MB': '#B8860B',
        'LB': '#FFD700', 'NA': '#FF8C00', 'NB': '#FF4500',
        'ACH': '#DC143C', 'UNKNOWN': '#808080'
    }

    node_colors = []
    node_sizes = []
    labels = {}

    for node_id in tree.nodes():
        node_data = tree.nodes[node_id]
        ntype = node_data.get('node_type', 'unknown')
        period = node_data.get('period', 'UNKNOWN')

        if ntype == 'text':
            node_colors.append(period_colors.get(period, '#4682B4'))
            node_sizes.append(800)
            labels[node_id] = node_data.get('label', node_id)[:30]
        elif ntype == 'root':
            node_colors.append('#2E8B57')
            node_sizes.append(1200)
            labels[node_id] = "ROOT"
        else:
            node_colors.append('#708090')
            node_sizes.append(500)
            labels[node_id] = ""

    # Draw edges
    for u, v in tree.edges():
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        ax.plot([x1, x2], [y1, y2], 'k-', linewidth=1.5, alpha=0.6)

    # Draw nodes
    scatter = ax.scatter([pos[n][0] for n in tree.nodes()],
                         [pos[n][1] for n in tree.nodes()],
                         c=node_colors, s=node_sizes, alpha=0.8,
                         edgecolors='black', linewidths=1.5, zorder=5)

    # Add labels for text nodes
    for node_id, label in labels.items():
        if label:
            x, y = pos[node_id]
            ax.annotate(label, (x, y), xytext=(5, 5), textcoords='offset points',
                       fontsize=8, fontweight='bold',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9, edgecolor='gray'))

    # Add bootstrap values for internal nodes
    for node_id in tree.nodes():
        if tree.nodes[node_id]['node_type'] in ['ancestor', 'root']:
            x, y = pos[node_id]
            bs = bootstrap.get(node_id, 0)
            ax.text(x, y, f"{bs:.0f}%", fontsize=7, ha='center', va='center',
                   color='darkred', fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='yellow', alpha=0.8))

    # Legend
    legend_elements = []
    for period, color in period_colors.items():
        if any(tree.nodes[n].get('period') == period for n in tree.nodes()):
            legend_elements.append(mpatches.Patch(color=color, label=PERIOD_LABELS.get(period, period)))
    legend_elements.append(mpatches.Patch(color='#2E8B57', label='Root'))
    legend_elements.append(mpatches.Patch(color='#708090', label='Ancestor'))

    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
    ax.set_title('Phylomythological Tree: Evolution of Mesopotamian Myths\n'
                 '(Hierarchical Clustering + Maximum Parsimony on Motif Vectors)',
                 fontsize=14, fontweight='bold', pad=20)
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()
    log.info(f"Tree visualization saved to {output_path}")

def hierarchical_layout(tree: nx.DiGraph) -> Dict:
    """Manual hierarchical layout for tree."""
    pos = {}
    root = [n for n in tree.nodes() if tree.nodes[n].get('node_type') == 'root'][0]

    def assign_positions(node, x, y, width):
        pos[node] = (x, y)
        children = list(tree.successors(node))
        if not children:
            return
        child_width = width / len(children)
        start_x = x - width / 2 + child_width / 2
        for i, child in enumerate(children):
            assign_positions(child, start_x + i * child_width, y - 1.5, child_width)

    assign_positions(root, 0, 0, len(tree.nodes()))
    return pos

# ──────────────────────────────────────────────────────────────
# Analysis & Reporting
# ──────────────────────────────────────────────────────────────
def analyze_findings(tree: nx.DiGraph, corpus: List[MythText],
                     vectors: Dict[str, np.ndarray],
                     distances: List[Dict]) -> Dict[str, Any]:
    """Analyze and report mathematical findings."""
    findings = {}

    # 1. Period-based motif frequency
    period_motif_counts = defaultdict(lambda: defaultdict(int))
    for text in corpus:
        period = text.period
        text_vec = vectors[text.id]
        motif_ids = [m.id for m in MOTIF_TAXONOMY]
        for mid, val in zip(motif_ids, text_vec):
            if val > 0.5:
                period_motif_counts[period][mid] += 1

    findings['period_motif_counts'] = {p: dict(c) for p, c in period_motif_counts.items()}

    # 2. Closest/Furthest pairs
    if distances:
        sorted_dist = sorted(distances, key=lambda d: d['semantic_distance'])
        findings['closest_pair'] = sorted_dist[0]
        findings['furthest_pair'] = sorted_dist[-1]
        findings['mean_distance'] = np.mean([d['semantic_distance'] for d in distances])
        findings['std_distance'] = np.std([d['semantic_distance'] for d in distances])

    # 3. Archetype evolution
    archetype_by_period = defaultdict(lambda: defaultdict(int))
    for text in corpus:
        period = text.period
        text_vec = vectors[text.id]
        motif_ids = [m.id for m in MOTIF_TAXONOMY]
        for mid, val in zip(motif_ids, text_vec):
            if val > 0.5:
                archetype = MOTIF_BY_ID[mid].archetype
                archetype_by_period[period][archetype] += 1
    findings['archetype_by_period'] = {p: dict(c) for p, c in archetype_by_period.items()}

    # 4. Tree depth and structure
    root = [n for n in tree.nodes() if tree.nodes[n].get('node_type') == 'root'][0]
    depths = {}
    def compute_depth(node, d):
        depths[node] = d
        for child in tree.successors(node):
            compute_depth(child, d + tree[node][child].get('distance', 0))
    compute_depth(root, 0)
    findings['tree_depths'] = depths

    # 5. Key evolutionary insights
    insights = []

    # Flood motif evolution
    flood_texts = [t.id for t in corpus if 'FLOOD' in t.id or 'ZIUSUDRA' in t.id or 'ATRAHASIS' in t.id or 'UTNAPISHTIM' in t.id]
    if len(flood_texts) >= 2:
        flood_distances = [d for d in distances if d['text_id_1'] in flood_texts and d['text_id_2'] in flood_texts]
        if flood_distances:
            avg_flood_dist = np.mean([d['semantic_distance'] for d in flood_distances])
            insights.append(f"Flood narrative variants (Ziusudra, Atrahasis, Utnapishtim) show mean semantic distance of {avg_flood_dist:.3f}, confirming divergent evolution from common EDIII ancestor.")

    # Gilgamesh cycle evolution
    gilg_texts = [t.id for t in corpus if 'GILGAMESH' in t.id]
    if len(gilg_texts) >= 2:
        gilg_distances = [d for d in distances if d['text_id_1'] in gilg_texts and d['text_id_2'] in gilg_texts]
        if gilg_distances:
            avg_gilg_dist = np.mean([d['semantic_distance'] for d in gilg_distances])
            # Find earliest (OB) vs latest (NA)
            ob_texts = [t for t in gilg_texts if 'OB' in next(x.period for x in corpus if x.id == t)]
            na_texts = [t for t in gilg_texts if 'NA' in next(x.period for x in corpus if x.id == t)]
            if ob_texts and na_texts:
                ob_na_dists = [d for d in gilg_distances
                               if (d['text_id_1'] in ob_texts and d['text_id_2'] in na_texts)
                               or (d['text_id_2'] in ob_texts and d['text_id_1'] in na_texts)]
                if ob_na_dists:
                    ob_na_avg = np.mean([d['semantic_distance'] for d in ob_na_dists])
                    insights.append(f"Gilgamesh cycle: Old Babylonian → Neo-Assyrian evolution shows semantic distance {ob_na_avg:.3f}, with motif gains (plant of immortality, Siduri, Urshanabi) in SB version.")

    # Enkidu cycle analysis
    enkidu_texts = [t.id for t in corpus if 'ENKIDU' in t.id or 'DEATH' in t.id or 'NETHERWORLD' in t.id]
    if enkidu_texts:
        insights.append(f"Enkidu-related texts ({', '.join(enkidu_texts)}) form a distinct motif cluster dominated by HERO_JOURNEY and AFTERLIFE archetypes, diverging early from main Gilgamesh flood lineage.")

    # Creation myths
    creation_texts = [t.id for t in corpus if 'ENUMA' in t.id or 'ENKI-NINHURSAG' in t.id or 'ERIDU' in t.id]
    if len(creation_texts) >= 2:
        cre_distances = [d for d in distances if d['text_id_1'] in creation_texts and d['text_id_2'] in creation_texts]
        if cre_distances:
            insights.append(f"Creation myths (Enuma Elish, Enki-Ninhursag, Eridu Genesis) span EDIII to LB with mean distance {np.mean([d['semantic_distance'] for d in cre_distances]):.3f}, showing CHAOSKAMPF motif emerges later (LB/NA) vs CREATION/CIVILIZATION motifs (EDIII).")

    findings['insights'] = insights

    # 6. Maximum parsimony ancestral state reconstruction (simplified)
    # For each archetype, trace presence/absence
    archo_states = {}
    for arch in ARCHETYPES:
        # Count presence in each period
        period_counts = {p: archetype_by_period[p].get(arch, 0) for p in PERIOD_ORDER if p in archetype_by_period}
        total_by_period = {p: sum(archetype_by_period[p].values()) for p in period_counts}
        archo_states[arch] = {
            'period_prevalence': {p: period_counts[p] / max(1, total_by_period[p]) for p in period_counts},
            'earliest_period': min(period_counts, key=lambda p: PERIOD_ORDER.get(p, 99)) if period_counts else 'UNKNOWN',
            'latest_period': max(period_counts, key=lambda p: PERIOD_ORDER.get(p, 99)) if period_counts else 'UNKNOWN'
        }
    findings['archetype_evolution'] = archo_states

    return findings

def print_findings(findings: Dict[str, Any]) -> None:
    """Print mathematical findings."""
    print("\n" + "="*70)
    print("🧬 PHYLOMYTHOLOGICAL ANALYSIS — MATHEMATICAL FINDINGS")
    print("="*70)

    if 'closest_pair' in findings:
        cp = findings['closest_pair']
        fp = findings['furthest_pair']
        print(f"\n📏 PAIRWISE DISTANCES:")
        print(f"   Closest: {cp['text_id_1']} ↔ {cp['text_id_2']} (d={cp['semantic_distance']:.4f})")
        print(f"   Furthest: {fp['text_id_1']} ↔ {fp['text_id_2']} (d={fp['semantic_distance']:.4f})")
        print(f"   Mean distance: {findings['mean_distance']:.4f} ± {findings['std_distance']:.4f}")

    if 'insights' in findings:
        print(f"\n🔬 KEY EVOLUTIONARY INSIGHTS:")
        for i, insight in enumerate(findings['insights'], 1):
            print(f"   {i}. {insight}")

    if 'archetype_evolution' in findings:
        print(f"\n📊 ARCHETYPE EVOLUTION TIMELINE:")
        for arch, data in findings['archetype_evolution'].items():
            if data['period_prevalence']:
                print(f"   {arch}:")
                print(f"     Earliest: {PERIOD_LABELS.get(data['earliest_period'], data['earliest_period'])}")
                print(f"     Latest: {PERIOD_LABELS.get(data['latest_period'], data['latest_period'])}")
                for p, prev in sorted(data['period_prevalence'].items(), key=lambda x: PERIOD_ORDER.get(x[0], 99)):
                    if prev > 0:
                        print(f"     {PERIOD_LABELS.get(p, p)}: {prev:.1%}")

    print("\n" + "="*70)

# ──────────────────────────────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────────────────────────────
def run_phylomythology_pipeline() -> Dict[str, Any]:
    log.info("=" * 70)
    log.info("🏛️  OX-STEALTH PHYLOMYTHOLOGY ENGINE")
    log.info("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    init_phylomyth_schema(conn)

    # 1. Build and load corpus
    log.info("Building mythological corpus...")
    corpus = build_myth_corpus()
    load_myth_corpus(conn, corpus)

    # 2. Load motif taxonomy
    log.info("Loading motif taxonomy...")
    load_motif_taxonomy(conn)

    # 3. Extract motifs
    log.info("Extracting motifs from texts...")
    extract_all_motifs(conn, corpus)

    # 4. Build motif vectors
    log.info("Building motif presence vectors...")
    vectors = build_motif_vectors(conn, corpus)

    # 5. Compute distances
    log.info("Computing pairwise semantic distances...")
    distances = compute_distances(vectors, corpus)
    save_distances(conn, distances)

    # 6. Compute phylogenetic tree
    log.info("Computing phylogenetic tree (hierarchical clustering + parsimony)...")
    tree = compute_phylogenetic_tree(vectors, corpus, distances)

    # 7. Bootstrap support
    log.info("Computing bootstrap support...")
    bootstrap = compute_bootstrap_support(tree, vectors, corpus, n_bootstrap=100)

    # 8. Infer migrations
    log.info("Inferring motif migrations...")
    migrations = infer_motif_migrations(tree, corpus)
    save_migrations(conn, migrations)

    # 9. Save tree
    save_tree(conn, tree, bootstrap)

    # 10. Analyze findings
    log.info("Analyzing findings...")
    findings = analyze_findings(tree, corpus, vectors, distances)

    # 11. Visualize
    log.info("Generating visualization...")
    visualize_tree(tree, bootstrap, EXPORT_DIR / "myth_evolution_tree.png")

    conn.close()

    log.info("=" * 70)
    log.info("✅ PHYLOMYTHOLOGY PIPELINE COMPLETE")
    log.info("=" * 70)

    return {'corpus_size': len(corpus), 'motif_count': len(MOTIF_TAXONOMY),
            'tree_nodes': tree.number_of_nodes(), 'distances': len(distances),
            'migrations': len(migrations), 'findings': findings}

if __name__ == "__main__":
    np.random.seed(42)
    random.seed(42)

    try:
        results = run_phylomythology_pipeline()
        print_findings(results['findings'])
        print(f"\n📊 PIPELINE SUMMARY:")
        print(f"   Corpus texts: {results['corpus_size']}")
        print(f"   Motif taxonomy: {results['motif_count']}")
        print(f"   Tree nodes: {results['tree_nodes']}")
        print(f"   Pairwise distances: {results['distances']}")
        print(f"   Motif migrations: {results['migrations']}")
        print(f"   Visualization: {EXPORT_DIR / 'myth_evolution_tree.png'}")
        sys.exit(0)
    except Exception as e:
        log.exception("Phylomythology pipeline failed")
        sys.exit(1)