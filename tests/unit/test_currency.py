"""Currency / price parsing tests."""
from commercial_ai.normalization.currency import parse_price


def test_colombian_dot_group_sep():
    assert parse_price("$499.900") == {"value": 499900, "currency": "COP"}


def test_colombian_comma_group_sep():
    assert parse_price("$499,900") == {"value": 499900, "currency": "COP"}


def test_currency_token_cop():
    assert parse_price("499900 COP") == {"value": 499900, "currency": "COP"}


def test_european_decimal_comma():
    assert parse_price("$1.299,90") == {"value": 1299.90, "currency": "COP"}


def test_us_decimal_dot():
    assert parse_price("1,299.90 USD") == {"value": 1299.90, "currency": "USD"}


def test_large_price():
    assert parse_price("$3.499.900") == {"value": 3499900, "currency": "COP"}


def test_unparseable():
    assert parse_price("Consultar") is None
    assert parse_price("") is None
    assert parse_price(None) is None


def test_numeric_input():
    assert parse_price(499900) == {"value": 499900.0, "currency": "COP"}
