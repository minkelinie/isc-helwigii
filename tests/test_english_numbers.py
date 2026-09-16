"""English surface-number recognition, not semantic quantity alignment."""

import pytest

from isc_helwigii.english_numbers import number_word_spans


@pytest.mark.parametrize(
    "text,value",
    [
        ("three sheep", 3),
        ("SEVEN oxen", 7),
        ("twenty-three cows", 23),
        ("ninety six workdays", 96),
        ("one hundred five rams", 105),
        ("one hundred and five rams", 105),
        ("one thousand two hundred and thirty-two ewes", 1232),
        ("one thousand and seven sheep", 1007),
        ("six thousand thirty-nine sheep", 6039),
        ("seventh day", 7),
        ("House-twenty-first-day", 21),
        ("one hundred and third day", 103),
        ("one thousandth tablet", 1000),
    ],
)
def test_recognizes_whole_cardinal_or_ordinal_expression(text, value):
    found, unassessed = number_word_spans(text)
    assert len(found) == 1
    assert found[0]["value"] == value
    assert text[found[0]["start"] : found[0]["end"]] == found[0]["text"]
    assert unassessed == []


@pytest.mark.parametrize(
    "text",
    [
        "three point five sheep",
        "one half sheep",
        "one-third sheep",
        "two thirds sheep",
        "one hundred and a half sheep",
        "minus three sheep",
        "negative three sheep",
        "-three sheep",
        "−three sheep",
        "one million sheep",
        "one dozen sheep",
        "one hundred hundred sheep",
        "twenty thirteen sheep",
        "one thousand two thousand sheep",
        "three and two sheep",
        "3 hundred sheep",
        "three hundred and 5 sheep",
    ],
)
def test_unsupported_phrases_are_not_partially_recognized(text):
    found, unassessed = number_word_spans(text)
    assert found == []
    assert len(unassessed) == 1
    assert "reason" in unassessed[0]


def test_distinct_commodities_punctuation_and_unicode_keep_separate_spans():
    text = "𒀭: three sheep and two oxen; twenty-three lambs."
    found, unassessed = number_word_spans(text)
    assert [x["value"] for x in found] == [3, 2, 23]
    assert [x["text"] for x in found] == ["three", "two", "twenty-three"]
    assert not unassessed
    for item in found:
        assert text[item["start"] : item["end"]] == item["text"]


def test_number_word_is_not_matched_inside_another_word():
    found, unassessed = number_word_spans("someone, firstborn, threescore, twentyish, three3")
    assert found == [] and unassessed == []


def test_punctuation_keeps_list_items_separate():
    found, unassessed = number_word_spans("one, two; three. Four!")
    assert [x["value"] for x in found] == [1, 2, 3, 4]
    assert not unassessed


@pytest.mark.parametrize(
    "text",
    [
        "− three sheep",
        "- three sheep",
        "one‑third of a mina",
        "a third of a mina",
        "two twelfths of a mina",
        "one and ½ minas",
        "1/three of a mina",
        "one/hundred sheep",
        "one⁄three of a mina",
        "two hundredths of a mina",
        "one hundredth of a mina",
        "one thousandth of a mina",
        "one quadrillion sheep",
    ],
)
def test_review_regressions_keep_fraction_and_negative_markers_in_the_phrase(text):
    found, unassessed = number_word_spans(text)
    assert found == []
    assert len(unassessed) == 1
    item = unassessed[0]
    assert text[item["start"] : item["end"]] == item["text"]
    assert item["start"] == 0


def test_typographic_word_hyphen_and_article_before_ordinal_have_distinct_meanings():
    found, unassessed = number_word_spans("twenty‑three sheep; the third tablet")
    assert [x["value"] for x in found] == [23, 3]
    assert not unassessed
