"""Deterministic review aids; these tests do not establish translation accuracy."""

import hashlib

import pytest

from isc_helwigii.translation_quality import assess_translation, render_quality_text


def check(source, target, **options):
    return assess_translation(source, target, source_language="sux", **options)


def test_detects_recorded_1232_to_132_error_without_changing_text():
    source = "2(u) 3(disz) ab2 4(disz) gu4 2(gesz'u) 3(u) 2(disz) u8"
    target = "23 cows, 4 oxen, 132 ewes"
    report = check(source, target)
    numbers = report["quantities"]
    assert numbers["status"] == "attention"
    assert [q["value"] for q in numbers["observations"]] == [23, 4, 1232]
    missing = [q for q in numbers["observations"] if q["status"] == "not_found"]
    assert [q["value"] for q in missing] == [1232]
    assert source[missing[0]["start"] : missing[0]["end"]] == "2(gesz'u) 3(u) 2(disz)"
    assert report["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert report["translation_sha256"] == hashlib.sha256(target.encode()).hexdigest()
    assert "1232" in render_quality_text(report)
    assert "geen nauwkeurigheidsscore" in render_quality_text(report)


def test_embedded_seventh_day_is_not_confused_with_sign_indices():
    report = check(
        "2(disz)# gu4 niga 4(disz) gu4 e2-u4-7(disz) u4 5(disz)",
        "2 oxen, 4 oxen, House Day 1; day 5",
    )
    observations = report["quantities"]["observations"]
    assert [q["value"] for q in observations if q["status"] == "not_found"] == [7]
    assert len(report["quantities"]["unassessed"]) == 1


def test_value_presence_is_only_a_limited_check_and_respects_multiplicity():
    report = check("2(disz) gu4 2(disz) udu", "2 oxen and sheep")
    assert report["quantities"]["missing_count"] == 1
    same = check("2(gesz’u) 3(u) 2(diš) u8", "1,232 ewes")
    assert same["quantities"]["status"] == "limited"
    assert same["quantities"]["missing_count"] == 0
    assert check("7(disz)-kam u4", "7th day")["quantities"]["missing_count"] == 0


@pytest.mark.parametrize(
    "source",
    [
        "[1(gesz2) 3(u)] 2(disz) udu",
        "1(u)? 3(disz) udu",
        "n(u) 3(disz) udu",
        "1(u) [...] 3(disz) udu",
        "1/2(disz) udu",
        "1(asz) 3(barig) sze gur",
        "1(N01) 3(disz) udu",
        "1(disz) 1(u) udu",
        "igi-6(disz)-gal2",
    ],
)
def test_ambiguous_damaged_fractional_and_metrological_groups_are_unassessed(source):
    report = check(source, "Some sheep or grain")
    assert report["quantities"]["observations"] == []
    assert report["quantities"]["unassessed"]
    assert report["quantities"]["status"] == "not_assessed"


def test_newlines_do_not_join_separate_quantities():
    numbers = check("1(u)\n3(disz) udu", "10 oxen, 3 sheep")["quantities"]
    assert [q["value"] for q in numbers["observations"]] == [10, 3]


def test_target_sign_indices_and_fractions_do_not_satisfy_integer_counts():
    assert check("3(disz) udu", "sila3 and 3/4 sheep")["quantities"]["missing_count"] == 1
    assert check("3(disz) udu", "3.5 sheep")["quantities"]["missing_count"] == 1
    words = check("3(disz) udu", "three sheep")
    assert words["quantities"]["missing_count"] == 0
    assert words["quantities"]["observations"][0]["target_match"]["text"] == "three"


@pytest.mark.parametrize("options", [{"input_format": "cuneiform"}, {"target_language": "nl"}])
def test_unsupported_formats_are_not_treated_as_checked(options):
    report = check("2(disz) gu4", "2 oxen", **options)
    assert report["quantities"]["status"] == "not_assessed"
    assert not report["quantities"]["observations"]


def test_name_candidates_keep_exact_unicode_spans_without_invented_equivalents():
    source = "𒀭 ur-{d}namma uri5{ki}-ma {d}nin-{d}su4-an-na {gesz}gigir"
    report = check(source, "Ur-Namma, Ur and Ninsiana; a chariot")
    names = report["names"]
    assert names["status"] == "manual_review"
    assert [c["source"] for c in names["candidates"]] == [
        "ur-{d}namma",
        "uri5{ki}-ma",
        "{d}nin-{d}su4-an-na",
    ]
    for candidate in names["candidates"]:
        assert source[candidate["start"] : candidate["end"]] == candidate["source"]
        assert "translation" not in candidate
    assert check("ka-a2-na", "Ka-ana")["names"]["status"] == "not_assessed"


def test_checks_are_reproducible_and_have_no_score_or_approval():
    report = check("1(disz) gu4", "1 ox")
    assert report == check("1(disz) gu4", "1 ox")
    assert len(report["implementation_sha256"]) == 64
    assert "score" not in report and "accepted" not in str(report)


@pytest.mark.parametrize(
    "source",
    [
        "1(u) x 3(disz) udu",
        "1(u) XX 3(disz) udu",
        "1(u) . 3(disz) udu",
        "3(disz)] udu",
        "3(disz)⸣ udu",
        "3(disz)]# udu",
        "1.5(disz) udu",
        "1,5(disz) udu",
    ],
)
def test_review_regressions_cannot_certify_partial_source_quantities(source):
    report = check(source, "13 sheep, 3 sheep, 5 sheep")
    assert report["quantities"]["observations"] == []
    assert report["quantities"]["unassessed"]


@pytest.mark.parametrize(
    "target",
    [
        "3.5kg of wool",
        ".3 sheep",
        "-3 sheep",
        "−3 sheep",
        "1/3kg wool",
        "3e2 sheep",
        "1,003kg wool",
        "3/4kg wool",
    ],
)
def test_review_regressions_never_match_part_of_a_target_number(target):
    report = check("3(disz) udu", target)
    assert report["quantities"]["missing_count"] == 1


def test_sentence_punctuation_and_literal_unit_indices_still_work():
    assert check("3(disz) udu", "Sheep: 3.")["quantities"]["missing_count"] == 0
    assert check("3(disz) udu", "3 sila3")["quantities"]["missing_count"] == 0
    assert check("e2-u4-7(disz)", "House-7th-day")["quantities"]["missing_count"] == 0


def test_word_numbers_match_whole_expressions_and_consume_each_occurrence_once():
    text = "𒀭 One thousand two hundred and thirty-two ewes; three oxen and 3 sheep."
    report = check("2(gesz'u) 3(u) 2(disz) u8 3(disz) gu4 3(disz) udu", text)
    numbers = report["quantities"]
    assert numbers["missing_count"] == 0
    assert report["method"] == "translation-quality-screen-v2"
    assert set(report["implementation_files"]) == {"translation_quality.py", "english_numbers.py"}
    matches = [q["target_match"] for q in numbers["observations"]]
    assert [m["text"] for m in matches] == ["One thousand two hundred and thirty-two", "three", "3"]
    for match in matches:
        assert text[match["start"] : match["end"]] == match["text"]
    assert check("3(disz) gu4 3(disz) udu", "three animals")["quantities"]["missing_count"] == 1
    assert check("3(disz) gu4", "one hundred three oxen")["quantities"]["missing_count"] == 1


@pytest.mark.parametrize(
    "target", ["3 hundred oxen", "3 point five oxen", "three and 3 oxen", "− 3 oxen", "- 3 oxen"]
)
def test_unsupported_mixed_phrases_suppress_inner_digit_matches(target):
    report = check("3(disz) gu4", target)
    assert report["quantities"]["missing_count"] == 1
    assert report["quantities"]["target_unassessed"]
    rendered = render_quality_text(report)
    assert target.removesuffix(" oxen") in rendered
    assert "Doelgetal niet beoordeeld" in rendered


def test_rendering_historical_digit_only_report_does_not_reinterpret_it():
    import copy

    report = check("3(disz) udu", "three sheep")
    report["method"] = "translation-quality-screen-v1"
    q = report["quantities"]
    q.pop("target_unassessed")
    q["missing_count"] = 1
    q["observations"][0].update(target_match=None, status="not_found_as_digits")
    before = copy.deepcopy(report)
    rendered = render_quality_text(report)
    assert "NIET ALS HETZELFDE CIJFER TERUGGEVONDEN" in rendered
    assert report == before
