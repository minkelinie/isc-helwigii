import pytest

from isc_helwigii.evaluation import evaluate_labels, grouped_split


def test_family_and_duplicate_texts_cannot_leak():
    rows = [
        {"id": "a", "family": "f1", "text": "a b"},
        {"id": "b", "family": "f1", "text": "x"},
        {"id": "c", "family": "f2", "text": "a b"},
        {"id": "d", "family": "f2", "text": "y"},
    ]
    split = grouped_split(rows, seed=42)
    assert split == grouped_split(list(reversed(rows)), seed=42)
    assert len({split["assignments"][r["id"]] for r in rows}) == 1
    with pytest.raises(ValueError):
        grouped_split([{"id": "x", "text": "a"}])


def test_metrics_include_abstention_and_empty_data():
    result = evaluate_labels({"a": "letter", "b": "myth"}, {"a": "letter", "b": None})
    assert result["accuracy_all"] == 0.5
    assert result["coverage"] == 0.5
    assert result["accuracy_answered"] == 1
    assert evaluate_labels({}, {})["accuracy_all"] is None
    with pytest.raises(ValueError):
        evaluate_labels({"a": "letter"}, {"extra": "myth"})
