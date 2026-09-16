"""Bounded English surface-number grammar with exact, original-text spans.

Recognize complete cardinal/ordinal phrases from zero through 999,999. Never
salvage smaller values from an unsupported numeric phrase. This is lexical
evidence only: e.g. 'one' may be a pronoun and 'second' may describe a quality.
"""

import hashlib
import re
from pathlib import Path

IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SMALL = dict(
    enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
)
CARDINAL = {word: value for value, word in SMALL.items()}
TENS = dict(
    zip(
        "twenty thirty forty fifty sixty seventy eighty ninety".split(),
        range(20, 100, 10),
        strict=True,
    )
)
ORDINAL = dict(
    zip(
        "first second third fourth fifth sixth seventh eighth ninth tenth eleventh "
        "twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth "
        "nineteenth".split(),
        range(1, 20),
        strict=True,
    )
)
ORDINAL.update(
    dict(
        zip(
            "twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth".split(),
            range(20, 100, 10),
            strict=True,
        )
    )
)
SCALES = {"hundred", "hundredth", "thousand", "thousandth"}
UNSUPPORTED = {
    "half",
    "halves",
    "quarter",
    "quarters",
    "thirds",
    "fourths",
    "fifths",
    "sixths",
    "sevenths",
    "eighths",
    "ninths",
    "tenths",
    "point",
    "minus",
    "negative",
    "million",
    "millionth",
    "billion",
    "billionth",
    "trillion",
    "dozen",
    "dozens",
    "score",
    "scores",
    "over",
}
UNSUPPORTED.update(word + "s" for word in set(ORDINAL) | {"hundredth", "thousandth"})
LEXICON = set(CARDINAL) | set(TENS) | set(ORDINAL) | SCALES | UNSUPPORTED
CONNECTORS = {"and", "a"}
TOKEN = re.compile(r"\w+(?:[.,/]\d+)*")
GAP = re.compile(r"[ \t\n\r\u00a0‐‑/⁄-]+")
SIGN = re.compile(r"[+−-]\s*$")


def _number_word(word):
    return word in LEXICON or word.endswith(("illion", "illions", "illionth", "illionths"))


def _under_hundred(words):
    if len(words) == 1:
        word = words[0]
        if word in ORDINAL:
            return ORDINAL[word], True
        if word in CARDINAL or word in TENS:
            return CARDINAL.get(word, TENS.get(word)), False
    if len(words) == 2 and words[0] in TENS:
        unit = _under_hundred(words[1:])
        if unit and 1 <= unit[0] <= 9:
            return TENS[words[0]] + unit[0], unit[1]
    return None


def _under_thousand(words):
    if len(words) >= 2 and 1 <= CARDINAL.get(words[0], -1) <= 9:
        if words[1] == "hundredth" and len(words) == 2:
            return CARDINAL[words[0]] * 100, True
        if words[1] == "hundred":
            value = CARDINAL[words[0]] * 100
            if len(words) == 2:
                return value, False
            rest = words[3:] if words[2] == "and" else words[2:]
            tail = _under_hundred(rest)
            if tail and tail[0] > 0:
                return value + tail[0], tail[1]
            return None
    return _under_hundred(words)


def _parse(words):
    for scale in ("thousand", "thousandth"):
        if scale not in words:
            continue
        split = words.index(scale)
        head = _under_thousand(words[:split])
        if not head or head[1] or head[0] == 0:
            return None
        if split == len(words) - 1:
            return head[0] * 1000, scale == "thousandth"
        if scale == "thousandth":
            return None
        rest = words[split + 1 :]
        if rest[0] == "and":
            rest = rest[1:]
        tail = _under_thousand(rest)
        if tail and tail[0] > 0:
            return head[0] * 1000 + tail[0], tail[1]
        return None
    return _under_thousand(words)


def number_word_spans(text):
    """Return (recognized phrases, unsupported numeric phrases), without edits.

    Mixed digits/words, fractions, negatives and larger scales are captured as
    unsupported. Consumers must suppress digit matches inside those spans too.
    """
    tokens = list(TOKEN.finditer(text))
    found, unassessed = [], []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        word = token[0].lower()
        if not _number_word(word) and word != "a" and not word[0].isnumeric():
            i += 1
            continue
        group = [token]
        j = i + 1
        while j < len(tokens):
            next_word = tokens[j][0].lower()
            if not GAP.fullmatch(text[group[-1].end() : tokens[j].start()]):
                break
            if (
                not _number_word(next_word)
                and next_word not in CONNECTORS
                and not next_word[0].isnumeric()
            ):
                break
            group.append(tokens[j])
            j += 1
        i = j
        # A conjunction/article before a commodity is not part of its count.
        while group and group[-1][0].lower() in CONNECTORS:
            group.pop()
        if not group:
            continue
        start, end = group[0].start(), group[-1].end()
        sign = SIGN.search(text[:start])
        signed = sign is not None and not (
            sign[0] == "-" and sign.start() > 0 and text[sign.start() - 1].isalpha()
        )
        fraction = "/" in text[start:end] or "⁄" in text[start:end]
        if not signed and not fraction and not any(_number_word(t[0].lower()) for t in group):
            continue
        if signed:
            start = sign.start()
        item = {"start": start, "end": end, "text": text[start:end]}
        number = None if signed or fraction else _parse([t[0].lower() for t in group])
        if number and number[1] and re.match(r"\s+of\b", text[end:], re.IGNORECASE):
            number = None  # e.g. 'one hundredth of a mina' may denote a fraction.
        if number is None:
            unassessed.append(
                {
                    **item,
                    "reason": "Niet ondersteunde Engelse getaluitdrukking; "
                    "geen deelwaarden overgenomen.",
                }
            )
        else:
            found.append(
                {
                    **item,
                    "value": number[0],
                    "notation": "ordinal_words" if number[1] else "cardinal_words",
                }
            )
    return found, unassessed
