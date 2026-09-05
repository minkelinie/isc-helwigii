import pytest

from isc_helwigii.evaluation import evaluate_rankings, evaluate_readings


def test_rank_metrics_penalize_missing_results_and_validate_duplicates():
    report = evaluate_rankings({"q1": ["a", "b"], "q2": ["c"]}, {"q1": ["x", "a", "b"]}, k=2)
    assert report["mrr"] == 0.25
    assert report["mean_recall_at_k"] == 0.25
    assert report["mean_precision_at_k"] == 0.25
    assert report["n_evaluable"] == 2
    with pytest.raises(ValueError):
        evaluate_rankings({"q1": ["a"]}, {"q1": ["a", "a"]})


def test_no_positive_gold_is_not_a_zero_score():
    report = evaluate_rankings({"q": []}, {})
    assert report["mrr"] is None
    assert report["n_evaluable"] == 0


def test_reading_error_rates_include_insertions_and_missing_output():
    report = evaluate_readings({"a": "ab", "b": "cd"}, {"a": "ax", "b": None})
    assert report["character_error_rate"] == 0.75
    assert report["coverage"] == 0.5
    assert report["word_error_rate"] == 1
    assert evaluate_readings({"a": ""}, {"a": "extra"})["character_error_rate"] is None
