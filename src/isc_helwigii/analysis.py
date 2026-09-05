"""Inspectable exploratory baselines, not calibrated historical inference."""

import math
import re
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations


def tokens(text):
    # Retain philological indices and brackets; never delete globally matching substrings.
    text = unicodedata.normalize("NFC", text).casefold()
    return [
        word
        for word in re.split(r"\s+", text.strip())
        if word and word not in {"x", "...", "…", "[...]", "[…]", "xxx"}
    ]


def text_similarity(a, b):
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return {
            "status": "abstained",
            "reason": "no readable tokens in one or both passages",
            "method": "token-jaccard-sequence-v1",
        }
    sa, sb = set(left), set(right)
    sequence = SequenceMatcher(None, left, right, autojunk=False)
    return {
        "status": "exploratory",
        "method": "token-jaccard-sequence-v1",
        "jaccard": len(sa & sb) / len(sa | sb),
        "sequence_ratio": sequence.ratio(),
        "shared_tokens": sorted(sa & sb),
        "alignment": [list(item) for item in sequence.get_opcodes()],
        "left_tokens": left,
        "right_tokens": right,
        "limitation": "lexical overlap is neither a physical join nor evidence of common ancestry",
    }


def valid_language(language):
    return (
        isinstance(language, str)
        and bool(language.strip())
        and language.strip().casefold() != "unknown"
    )


def rank_parallels(query, records, language, limit=20):
    if not valid_language(language):
        return []
    results = []
    for record in records:
        if record.get("language") != language:
            continue
        result = text_similarity(query, record.get("text", ""))
        if result.get("jaccard", 0) > 0:
            results.append({"id": record["id"], **result})
    return sorted(results, key=lambda r: (-r["jaccard"], -r["sequence_ratio"], r["id"]))[:limit]


def translation_memory(query, entries, language, target_language):
    candidates = []
    if valid_language(language) and valid_language(target_language) and query.strip():
        for entry in entries:
            # Exact NFC passage match, not bag-of-words or generated translation.
            if (
                entry.get("status") == "accepted"
                and entry.get("evidence")
                and entry.get("language") == language
                and entry.get("target_language") == target_language
                and unicodedata.normalize("NFC", entry.get("source_text", "")).strip()
                == unicodedata.normalize("NFC", query).strip()
            ):
                candidates.append(entry)
    return {
        "method": "reviewed-exact-translation-memory-v1",
        "status": "attested-parallel" if candidates else "abstained",
        "candidates": candidates,
        "limitation": "an accepted parallel is an editorial suggestion; its context must be checked",
    }


def validate_material(sample):
    if not isinstance(sample, dict):
        raise ValueError("material sample must be an object")
    for key in ("method", "laboratory", "calibration", "reference_group"):
        if not isinstance(sample.get(key), str) or not sample[key].strip():
            raise ValueError(f"material sample requires {key}")
    measurements = sample.get("measurements")
    if not isinstance(measurements, dict) or not measurements:
        raise ValueError("material sample requires measurements")
    for element, measurement in measurements.items():
        if not isinstance(element, str) or not element or not isinstance(measurement, dict):
            raise ValueError("named measurements required")
        for key in ("value", "uncertainty"):
            value = measurement.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("finite non-negative concentrations and uncertainty required")
        if (
            measurement["uncertainty"] == 0
            or not isinstance(measurement.get("unit"), str)
            or not measurement["unit"].strip()
        ):
            raise ValueError("positive one-sigma uncertainty and a unit required")
    return sample


def compare_materials(a, b):
    if a is None or b is None:
        return {
            "status": "abstained",
            "reason": "documented lab measurements missing",
            "method": "measurement-distance-v1",
        }
    validate_material(a)
    validate_material(b)
    for field in ("method", "laboratory", "calibration"):
        if a[field] != b[field]:
            return {
                "status": "abstained",
                "reason": f"incompatible {field}",
                "method": "measurement-distance-v1",
            }
    components = []
    for element in sorted(a["measurements"].keys() & b["measurements"].keys()):
        x, y = a["measurements"][element], b["measurements"][element]
        if x["unit"] != y["unit"]:
            continue
        standard_error = math.hypot(x["uncertainty"], y["uncertainty"])
        components.append(
            {
                "element": element,
                "unit": x["unit"],
                "difference": x["value"] - y["value"],
                "standardized_difference": (x["value"] - y["value"]) / standard_error,
            }
        )
    if not components:
        return {
            "status": "abstained",
            "reason": "no shared analytes with identical units",
            "method": "measurement-distance-v1",
        }
    return {
        "status": "exploratory",
        "method": "measurement-distance-v1",
        "components": components,
        "standardized_rms": math.sqrt(
            sum(c["standardized_difference"] ** 2 for c in components) / len(components)
        ),
        "assumptions": [
            "independent measurements",
            "comparable calibration",
            "one-sigma uncertainties",
        ],
        "limitation": "no compositional correction or correlated-error model; this distance does not identify geographic origin",
    }


def motif_network(witnesses):
    if len({w["id"] for w in witnesses}) != len(witnesses):
        raise ValueError("witness IDs must be unique")
    unknown = [w["id"] for w in witnesses if w.get("motifs") is None]
    known = [w for w in witnesses if w.get("motifs") is not None]
    edges = []
    for a, b in combinations(sorted(known, key=lambda w: w["id"]), 2):
        sa, sb = set(a["motifs"]), set(b["motifs"])
        shared = sa & sb
        if shared:
            edges.append(
                {
                    "source": a["id"],
                    "target": b["id"],
                    "shared": sorted(shared),
                    "jaccard": len(shared) / len(sa | sb),
                }
            )
    return {
        "status": "exploratory",
        "method": "motif-cooccurrence-v1",
        "nodes": [w["id"] for w in witnesses],
        "edges": edges,
        "unknown": unknown,
        "mechanisms_to_test": [
            "inheritance",
            "diffusion",
            "convergence",
            "contamination",
            "preservation bias",
        ],
        "limitation": "undirected overlap network; supports neither an ancestral reconstruction nor a date by itself",
    }


def date_overlap(a, b):
    if a is None or b is None:
        return {"status": "abstained", "reason": "date interval missing"}
    for interval in (a, b):
        if (
            not isinstance(interval, (list, tuple))
            or len(interval) != 2
            or any(type(v) is not int for v in interval)
            or interval[0] > interval[1]
        ):
            raise ValueError(
                "date interval must be [earliest,latest] in astronomical year numbering"
            )
    start, end = max(a[0], b[0]), min(a[1], b[1])
    return {
        "status": "exploratory",
        "overlap": [start, end] if start <= end else None,
        "limitation": "witness dates constrain attestations, not the birth or oral age of a myth",
    }
