"""Deterministic evaluation with explicit family and duplicate grouping."""

import hashlib
import unicodedata


def evaluate_rankings(gold, predicted, k=10):
    if (
        not isinstance(gold, dict)
        or not isinstance(predicted, dict)
        or type(k) is not int
        or k < 1
        or set(predicted) - set(gold)
    ):
        raise ValueError("gold/predicted mappings, matching IDs and positive k required")
    for values in list(gold.values()) + list(predicted.values()):
        if (
            not isinstance(values, list)
            or any(not isinstance(v, str) or not v for v in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError("unique non-empty artifact identifiers required in each ranking")
    rows = []
    for query, relevant in gold.items():
        if not relevant:
            continue
        ranking = predicted.get(query, [])[:k]
        hits = [i + 1 for i, key in enumerate(ranking) if key in relevant]
        rows.append(
            {
                "query": query,
                "precision_at_k": len(hits) / k,
                "recall_at_k": len(hits) / len(relevant),
                "reciprocal_rank": 1 / hits[0] if hits else 0,
            }
        )
    return {
        "method": "ranking-at-k-v1",
        "k": k,
        "n_queries": len(gold),
        "n_evaluable": len(rows),
        "per_query": rows,
        "mrr": sum(r["reciprocal_rank"] for r in rows) / len(rows) if rows else None,
        "mean_precision_at_k": sum(r["precision_at_k"] for r in rows) / len(rows) if rows else None,
        "mean_recall_at_k": sum(r["recall_at_k"] for r in rows) / len(rows) if rows else None,
        "limitation": "queries without known positives are excluded; relevance judgment completeness affects scores",
    }


def _edit_distance(left, right):
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def evaluate_readings(gold, predicted):
    if not isinstance(gold, dict) or not isinstance(predicted, dict) or set(predicted) - set(gold):
        raise ValueError("gold/predicted mappings with matching identifiers required")
    errors_chars = errors_words = chars = words = answered = 0
    for key, expected in gold.items():
        actual = predicted.get(key)
        if not isinstance(expected, str) or (actual is not None and not isinstance(actual, str)):
            raise ValueError("readings must be text or a null prediction")
        if len(expected) > 10000 or (actual is not None and len(actual) > 10000):
            raise ValueError("evaluate aligned passages of at most 10000 characters")
        answered += actual is not None
        expected = unicodedata.normalize("NFC", expected)
        actual = unicodedata.normalize("NFC", actual or "")
        errors_chars += _edit_distance(expected, actual)
        errors_words += _edit_distance(expected.split(), actual.split())
        chars += len(expected)
        words += len(expected.split())
    return {
        "method": "reading-edit-distance-v1",
        "n": len(gold),
        "character_errors": errors_chars,
        "reference_characters": chars,
        "word_errors": errors_words,
        "reference_words": words,
        "character_error_rate": errors_chars / chars if chars else None,
        "word_error_rate": errors_words / words if words else None,
        "coverage": answered / len(gold) if gold else None,
        "limitation": "orthographic edit distance evaluates readings, not semantic translation adequacy; rates may exceed 1",
    }


def grouped_split(records, seed=0):
    parent = {}
    for record in records:
        if (
            not isinstance(record.get("id"), str)
            or not record["id"]
            or not isinstance(record.get("family"), str)
            or not record["family"]
            or record["id"] in parent
        ):
            raise ValueError("unique IDs and explicit composition families required")
        parent[record["id"]] = record["id"]

    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key

    def union(a, b):
        a, b = root(a), root(b)
        parent[max(a, b)] = min(a, b)

    families, texts = {}, {}
    for record in sorted(records, key=lambda r: r["id"]):
        rid = record["id"]
        family = record["family"]
        if family in families:
            union(rid, families[family])
        families[family] = rid
        text = " ".join(unicodedata.normalize("NFC", record.get("text", "")).casefold().split())
        if text:
            if text in texts:
                union(rid, texts[text])
            texts[text] = rid
    assignments = {}
    for key in sorted(parent):
        bucket = int(hashlib.sha256(f"{seed}:{root(key)}".encode()).hexdigest(), 16) % 100
        assignments[key] = "train" if bucket < 80 else "dev" if bucket < 90 else "test"
    counts = {name: list(assignments.values()).count(name) for name in ("train", "dev", "test")}
    return {
        "method": "family-exact-duplicate-components-v1",
        "seed": seed,
        "assignments": assignments,
        "counts": counts,
        "limitation": "small corpora can have empty splits; near-duplicate detection requires additional editorial grouping",
    }


def evaluate_labels(gold, predicted):
    if not isinstance(gold, dict) or not isinstance(predicted, dict):
        raise ValueError("gold and predictions must be identifier-to-label objects")
    if set(predicted) - set(gold):
        raise ValueError("predictions contain identifiers absent from gold data")
    if any(not isinstance(label, str) or not label for label in gold.values()):
        raise ValueError("gold labels must be non-empty strings")
    if any(
        label is not None and (not isinstance(label, str) or not label)
        for label in predicted.values()
    ):
        raise ValueError("prediction must be a non-empty label or null for abstention")
    answered = {key: predicted.get(key) for key in gold if predicted.get(key) is not None}
    correct = sum(value == gold[key] for key, value in answered.items())
    confusion = {}
    for key, expected in gold.items():
        actual = predicted.get(key)
        confusion.setdefault(expected, {})[actual or "[abstained]"] = (
            confusion.setdefault(expected, {}).get(actual or "[abstained]", 0) + 1
        )
    return {
        "method": "categorical-with-abstention-v1",
        "n": len(gold),
        "answered": len(answered),
        "correct": correct,
        "coverage": len(answered) / len(gold) if gold else None,
        "accuracy_all": correct / len(gold) if gold else None,
        "accuracy_answered": correct / len(answered) if answered else None,
        "confusion": confusion,
    }
