"""Conservative, source-anchored review aids, never translation certification.

Only a small subset of qualified CDLI additive counts is interpreted. Other
metrologies, uncertain readings, fractions and positional notation need an expert.
Source offsets are Unicode code-point offsets relative to the selected passage.
"""

import hashlib
import re
from collections import defaultdict, deque
from fractions import Fraction
from pathlib import Path

from isc_helwigii.english_numbers import (
    IMPLEMENTATION_SHA256 as ENGLISH_NUMBERS_SHA256,
    number_word_spans,
)

METHOD = "translation-quality-screen-v2"
IMPLEMENTATION_FILES = {
    "translation_quality.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "english_numbers.py": ENGLISH_NUMBERS_SHA256,
}
_IMPLEMENTATION_SHA256 = hashlib.sha256(
    "".join(
        f"{name}:{checksum}\n" for name, checksum in sorted(IMPLEMENTATION_FILES.items())
    ).encode()
).hexdigest()
REFERENCES = [
    "https://cdli-gh.github.io/guides/lists.html#numeracy-and-counting",
    "https://cdli.earth/P101904",
    "https://oracc.museum.upenn.edu/doc/help/editinginatf/primer/",
]
WEIGHTS = {"disz": 1, "u": 10, "gesz2": 60, "gesz'u": 600}
ALIASES = {"diš": "disz", "geš2": "gesz2", "geš₂": "gesz2", "geš'u": "gesz'u"}
NUMERAL = re.compile(
    r"(?<![\w/.,])(?P<count>[0-9]+(?:[.,][0-9]+)?(?:/[0-9]+)?|n|x)"
    r"\((?P<sign>[^()\s]+)\)(?P<flags>[#?!*]*)"
)
JOIN = re.compile(r"[ \t\[\]⸢⸣⌈⌉.xX…]*")
DIGITS = re.compile(
    r"(?<![\w/.,+−])[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?"
    r"(?:/[0-9]+)?(?:st|nd|rd|th)?(?![\w/]|[.,][0-9])"
)
NAME_MARKER = re.compile(r"\{(?:d|m|f|ki)\}")
LIMITATIONS = [
    "Dit is een beperkte signalering, geen nauwkeurigheidsscore of goedkeuring.",
    "Getallen worden alleen onder de aanname van additieve CDLI-telnotatie gelezen "
    "(disz, u, gesz2, gesz'u); de onderzoeker moet het gebruikte maatstelsel bevestigen.",
    "De vergelijking zoekt dezelfde waarde in cijfernotatie en volledig uitgeschreven Engelse "
    "hoofd- en rangtelwoorden tot 999999. Breuken, gemengde notaties, grotere schalen, "
    "omrekeningen en impliciete aantallen vragen menselijke controle.",
    "Engelse woorden zoals 'one' en 'second' kunnen ook een andere functie hebben. "
    "Herkenning is woordelijk; het verband met de bron wordt niet vastgesteld.",
    "Een teruggevonden getal bewijst niet dat het bij het juiste dier, voorwerp of de juiste "
    "eenheid hoort. Toegevoegde aantallen, ontkenningen en weglatingen worden niet vastgesteld.",
    "Naamsignalen zijn woorden met {d}, {m}, {f} of {ki}; namen zonder zo'n markering "
    "en leesvarianten vragen afzonderlijke menselijke controle.",
]


def _span(text, start, end):
    return {"start": start, "end": end, "source": text[start:end]}


def _groups(source):
    groups = []
    for match in NUMERAL.finditer(source):
        if groups and JOIN.fullmatch(source[groups[-1][-1].end() : match.start()]):
            groups[-1].append(match)
        else:
            groups.append([match])
    return groups


def _quantity(group, source):
    start, end = group[0].start(), group[-1].end()
    while end < len(source) and source[end] in "]⸣⌉#?!*":
        end += 1
    result = _span(source, start, end)
    # Open editorial brackets can start before this particular numeral.
    prefix = source[:start]
    bracketed = any(
        prefix.count(left) > prefix.count(right)
        for left, right in (("[", "]"), ("⸢", "⸣"), ("⌈", "⌉"))
    )
    if bracketed or re.search(r"[\[\]⸢⸣⌈⌉#?.…]|\b[xX]+\b", result["source"]):
        return {**result, "reason": "Beschadigde, aangevulde of onzekere getallezing."}
    if re.search(r"igi-$", prefix) or source[end:].startswith("-gal"):
        return {**result, "reason": "Mogelijke breuknotatie; niet als geheel getal gelezen."}
    weights, total = [], 0
    for match in group:
        sign = match["sign"].replace("’", "'")
        sign = ALIASES.get(sign, sign)
        count = match["count"]
        if sign not in WEIGHTS or not count.isascii() or not count.isdigit() or len(count) > 2:
            return {**result, "reason": "Onbekend getal, breuk of niet ondersteund maatstelsel."}
        count = int(count)
        if not 1 <= count <= 9:
            return {**result, "reason": "Getalnotatie valt buiten de ondersteunde telconventie."}
        weights.append(WEIGHTS[sign])
        total += count * WEIGHTS[sign]
    if any(left <= right for left, right in zip(weights, weights[1:], strict=False)):
        return {**result, "reason": "Geen eenduidige aflopende additieve getalgroep."}
    return {**result, "value": total}


def _target_numbers(text):
    numbers = defaultdict(deque)
    words, unassessed = number_word_spans(text)
    candidates = list(words)
    for match in DIGITS.finditer(text):
        if any(
            item["start"] < match.end() and match.start() < item["end"]
            for item in words + unassessed
        ):
            continue
        # A word hyphen in House-7th-day is not a negative sign in -7 sheep.
        start = match.start()
        if start and text[start - 1] == "-" and not (start > 1 and text[start - 2].isalpha()):
            continue
        literal = re.sub(r"(?:st|nd|rd|th)$", "", match[0]).replace(",", "")
        try:
            number = Fraction(literal)
        except (ValueError, ZeroDivisionError):
            continue
        if number.denominator == 1:
            candidates.append(
                {
                    "value": int(number),
                    "start": match.start(),
                    "end": match.end(),
                    "text": match[0],
                    "notation": "digits",
                }
            )
    for item in sorted(candidates, key=lambda item: item["start"]):
        numbers[item["value"]].append({key: value for key, value in item.items() if key != "value"})
    return numbers, unassessed


def assess_translation(
    source, translation, *, source_language, target_language="en", input_format="transliteration"
):
    """Record literal evidence and explicit limits; never edit either input."""
    transliteration = input_format in ("transliteration", "complex-transliteration")
    supported = transliteration and source_language in ("sux", "akk") and target_language == "en"
    observations, unassessed, target_unassessed = [], [], []
    if supported:
        available, target_unassessed = _target_numbers(translation)
        for group in _groups(source):
            quantity = _quantity(group, source)
            if "reason" in quantity:
                unassessed.append(quantity)
                continue
            matches = available[quantity["value"]]
            match = matches.popleft() if matches else None
            observations.append(
                {
                    **quantity,
                    "target_match": match,
                    "status": "value_present" if match else "not_found",
                }
            )
    missing = sum(q["status"] == "not_found" for q in observations)
    status = "attention" if missing else "limited" if observations else "not_assessed"
    names = []
    if transliteration and source_language in ("sux", "akk"):
        for token in re.finditer(r"\S+", source):
            markers = sorted(set(NAME_MARKER.findall(token[0])))
            if markers:
                names.append({**_span(source, token.start(), token.end()), "markers": markers})
    return {
        "method": METHOD,
        "implementation_sha256": _IMPLEMENTATION_SHA256,
        "implementation_files": dict(IMPLEMENTATION_FILES),
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "translation_sha256": hashlib.sha256(translation.encode()).hexdigest(),
        "source_language": source_language,
        "target_language": target_language,
        "input_format": input_format,
        "offset_scope": "selected-source-passage; Unicode code points; end exclusive",
        "quantities": {
            "status": status,
            "checked_count": len(observations),
            "missing_count": missing,
            "observations": observations,
            "unassessed": unassessed,
            "target_unassessed": target_unassessed,
        },
        "names": {"status": "manual_review" if names else "not_assessed", "candidates": names},
        "limitations": list(LIMITATIONS),
        "references": list(REFERENCES),
    }


def render_quality_text(report):
    """Plain text for safe display and export, with no implied pass label."""
    quantities = report["quantities"]
    missing_label = (
        "hetzelfde cijfer"
        if report["method"] == "translation-quality-screen-v1"
        else "dezelfde waarde"
    )
    lines = [
        "Kwaliteitscontrole — beperkte signalering",
        report["limitations"][0],
        "Posities zijn relatief aan de geselecteerde bronpassage.",
    ]
    if not quantities["observations"]:
        lines.append("Aantallen: niet beoordeeld; geen ondersteunde getalgroepen vergeleken.")
    else:
        lines.append(
            f"Aantallen: {quantities['checked_count']} getalgroepen vergeleken; "
            f"{quantities['missing_count']} niet als {missing_label} teruggevonden."
        )
    for quantity in quantities["observations"]:
        match = quantity["target_match"]
        outcome = (
            f"waarde aanwezig als {match['text']!r} in de vertaling"
            if match
            else f"NIET ALS {missing_label.upper()} TERUGGEVONDEN"
        )
        lines.append(
            f"[{quantity['start']}–{quantity['end']}] {quantity['source']} "
            f"→ {quantity['value']}: {outcome}."
        )
    for item in quantities["unassessed"]:
        lines.append(
            f"Niet beoordeeld [{item['start']}–{item['end']}]: {item['source']} — {item['reason']}"
        )
    for item in quantities.get("target_unassessed", []):
        lines.append(
            f"Doelgetal niet beoordeeld [{item['start']}–{item['end']} in de vertaling: "
            f"{item['text']} — {item['reason']}"
        )
    candidates = report["names"]["candidates"]
    lines.append(
        "Naamsignalen: handmatig vergelijken; er is geen naamovereenkomst vastgesteld."
        if candidates
        else "Namen: niet beoordeeld; geen ondersteunde naamsignalen gevonden."
    )
    for candidate in candidates:
        lines.append(f"[{candidate['start']}–{candidate['end']}] {candidate['source']}")
    lines.extend(report["limitations"][1:])
    lines.extend(
        [
            f"Methode: {report['method']}",
            f"Implementatie SHA-256: {report['implementation_sha256']}",
        ]
    )
    return "\n".join(lines)
