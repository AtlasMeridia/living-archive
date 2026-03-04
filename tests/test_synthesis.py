"""Unit tests for synthesis helpers in src.synthesis."""

from src import synthesis


def test_normalize_date_and_precision():
    assert synthesis.normalize_date("1978-03-15") == ("1978-03-15", "day")
    assert synthesis.normalize_date("1978-03") == ("1978-03", "month")
    assert synthesis.normalize_date("1978") == ("1978", "year")
    assert synthesis.normalize_date("1970s") == ("1970", "decade")


def test_date_to_decade():
    assert synthesis.date_to_decade("1978-03-15") == "1970s"
    assert synthesis.date_to_decade("2001") == "2000s"
    assert synthesis.date_to_decade("unknown") is None


def test_extract_countries():
    assert synthesis.extract_countries("Taipei, Taiwan") == ["Taiwan"]
    assert synthesis.extract_countries("Rome, Italy") == ["Italy"]
    # Multiple countries in one free-text location should all be captured.
    assert synthesis.extract_countries(
        "Mediterranean cruise from Italy to Spain"
    ) == ["Italy", "Spain"]


def test_normalize_person_name_strips_titles_and_annotations():
    assert synthesis.normalize_person_name("Dr. Feng-Kuang Liu (patient)") == "feng kuang liu"
    assert synthesis.normalize_person_name("M. Grace Liu (劉彭美珠)") == "m grace liu"
