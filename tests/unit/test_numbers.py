"""Number / unit / bool extraction tests."""
from commercial_ai.normalization.numbers import (
    extract_number, parse_bool, parse_dimensions, parse_value_with_unit,
)


def test_extract_number_plain():
    assert extract_number("25600") == 25600


def test_extract_number_with_text():
    assert extract_number("106 g") == 106


def test_extract_number_group_sep():
    assert extract_number("1.000") == 1000


def test_extract_number_decimal():
    assert extract_number("0.5") == 0.5


def test_extract_number_none():
    assert extract_number("abc") is None
    assert extract_number(None) is None


def test_parse_value_with_unit_ms():
    assert parse_value_with_unit("1ms") == {"value": 1, "unit": "ms"}
    assert parse_value_with_unit("1 ms") == {"value": 1, "unit": "ms"}
    assert parse_value_with_unit("0.5 ms") == {"value": 0.5, "unit": "ms"}


def test_parse_value_with_unit_hz():
    assert parse_value_with_unit("1000 Hz") == {"value": 1000, "unit": "hz"}


def test_parse_value_with_unit_no_unit():
    assert parse_value_with_unit("25600") == {"value": 25600}


def test_parse_bool_spanish():
    assert parse_bool("Sí") is True
    assert parse_bool("No") is False
    assert parse_bool("si") is True


def test_parse_bool_english():
    assert parse_bool("yes") is True
    assert parse_bool("false") is False


def test_parse_bool_none():
    assert parse_bool(None) is None
    assert parse_bool("") is None
    assert parse_bool("maybe") is None


def test_parse_dimensions():
    d = parse_dimensions("120 x 60 x 40 mm")
    assert d == {"length": 120, "width": 60, "height": 40}


def test_parse_dimensions_partial():
    d = parse_dimensions("120 x 60")
    assert d["length"] == 120
    assert d["width"] == 60
    assert d["height"] is None
