import pytest

from isc_helwigii.analysis import (
    compare_materials,
    date_overlap,
    motif_network,
    rank_parallels,
    text_similarity,
    translation_memory,
)


def test_text_baseline_and_damage_abstention():
    assert text_similarity("a b", "a b")["jaccard"] == 1
    assert text_similarity("a b", "a c")["jaccard"] == pytest.approx(1 / 3)
    assert text_similarity("x ... [...]", "a")["status"] == "abstained"
    assert text_similarity("Šu", "šu")["jaccard"] == 1


def test_retrieval_separates_languages_and_ignores_empty_matches():
    rows = [
        {"id": "a", "text": "a b", "language": "akk"},
        {"id": "s", "text": "a b", "language": "sux"},
        {"id": "z", "text": "z", "language": "akk"},
    ]
    assert [r["id"] for r in rank_parallels("a b", rows, "akk")] == ["a"]
    assert rank_parallels("a", rows, "unknown") == []


def test_translation_memory_requires_accepted_exact_passage():
    entries = [
        {
            "id": "t",
            "source_text": "a b",
            "language": "akk",
            "target_language": "en",
            "text": "A B",
            "status": "pending",
            "evidence": ["source"],
        }
    ]
    assert translation_memory("a b", entries, "akk", "en")["status"] == "abstained"
    entries[0]["status"] = "accepted"
    assert translation_memory("a b", entries, "akk", "en")["candidates"][0]["text"] == "A B"
    assert translation_memory("a c", entries, "akk", "en")["status"] == "abstained"


def sample(value=10, unit="ppm", method="pXRF"):
    return {
        "method": method,
        "laboratory": "Lab",
        "calibration": "C1",
        "reference_group": "reference-A",
        "measurements": {"Fe": {"value": value, "uncertainty": 1, "unit": unit}},
    }


def test_material_comparison_has_units_and_no_origin_probability():
    result = compare_materials(sample(), sample(12))
    assert result["standardized_rms"] == pytest.approx(2**0.5)
    assert result["status"] == "exploratory"
    assert "probability" not in result
    assert compare_materials(sample(), sample(unit="%"))["status"] == "abstained"
    assert compare_materials(sample(), sample(method="INAA"))["status"] == "abstained"
    with pytest.raises(ValueError):
        compare_materials(sample(float("nan")), sample())


def test_network_distinguishes_unknown_and_absent():
    result = motif_network(
        [
            {"id": "a", "motifs": ["flood"]},
            {"id": "b", "motifs": ["flood", "boat"]},
            {"id": "c", "motifs": None},
            {"id": "d", "motifs": []},
        ]
    )
    assert result["edges"] == [{"source": "a", "target": "b", "shared": ["flood"], "jaccard": 0.5}]
    assert result["unknown"] == ["c"]
    assert "ancestor_date" not in result


def test_date_intervals_are_explicit_and_validated():
    assert date_overlap([-2000, -1900], [-1950, -1850])["overlap"] == [-1950, -1900]
    assert date_overlap([-2000, -1900], None)["status"] == "abstained"
    assert date_overlap([-2000, -1900], [-1800, -1700])["overlap"] is None
    with pytest.raises(ValueError):
        date_overlap([-1900, -2000], [-2000, -1000])
