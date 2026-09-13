"""Validate evaluation denominators and source attribution using synthetic pairs."""

import copy

import pytest

from isc_helwigii import translation_evaluation as evaluation


@pytest.fixture
def sample():
    return {
        "dataset": {
            "name": "Synthetic fixture",
            "source_url": "https://example.org/fixture",
            "license": "CC0 synthetic only",
            "split": "test fixture",
            "training_overlap": "not applicable; predictions mocked",
        },
        "examples": [
            {
                "id": str(i),
                "source_language": language,
                "text": text,
                "reference": "The synthetic king built a house.",
                "source_url": "https://example.org/fixture",
                "license": "CC0 synthetic only",
            }
            for i, (language, text) in enumerate(
                [
                    ("sux", "synthetic first"),
                    ("sumerian", "synthetic refusal"),
                    ("akk", "synthetic third"),
                ]
            )
        ],
    }


def test_scores_include_refusals_and_keep_languages_separate(sample, monkeypatch):
    pytest.importorskip("sacrebleu")
    original = copy.deepcopy(sample)
    calls = []

    def predict(text, **kwargs):
        calls.append(text)
        if "refusal" in text:
            raise ValueError("synthetic unreadable input")
        return {"text": "The synthetic king built a house.", "model": {"id": "synthetic"}}

    monkeypatch.setattr(evaluation, "translate_text", predict)
    report = evaluation.evaluate_translation_set(sample, model_dir="unused")
    assert sample == original
    assert len(calls) == 3
    sux = report["scores_by_language"]["sux"]
    assert (sux["count"], sux["generated"], sux["abstained"]) == (2, 1, 1)
    assert 0 < sux["metrics"]["chrF"]["score"] < 100
    assert report["scores_by_language"]["akk"]["metrics"]["chrF"]["score"] == 100
    assert "version:" in sux["metrics"]["BLEU"]["signature"]
    assert report["examples"][1]["prediction"] == ""
    assert report["examples"][1]["reason"] == "synthetic unreadable input"
    assert report["dataset"] == original["dataset"]


@pytest.mark.parametrize(
    "damage", ["no_provenance", "duplicate_id", "duplicate_source", "no_reference", "no_examples"]
)
def test_invalid_dataset_fails_before_inference(sample, monkeypatch, damage):
    if damage == "no_provenance":
        del sample["dataset"]["license"]
    elif damage == "duplicate_id":
        sample["examples"][1]["id"] = sample["examples"][0]["id"]
    elif damage == "duplicate_source":
        sample["examples"][1]["text"] = sample["examples"][0]["text"]
    elif damage == "no_reference":
        sample["examples"][0]["reference"] = " "
    else:
        sample["examples"] = []
    monkeypatch.setattr(
        evaluation, "translate_text", lambda *a, **kw: pytest.fail("invalid set reached model")
    )
    with pytest.raises(ValueError):
        evaluation.evaluate_translation_set(sample, model_dir="unused")
