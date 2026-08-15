"""Currency / price parsing.

Handles Colombian-style separators and a few international forms, e.g.:
    "$499.900"  -> 499900  (group sep '.', no decimals)
    "$499,900"  -> 499900  (group sep ',', no decimals)
    "499900 COP"-> 499900
    "$1.299,90" -> 1299.90 (group '.', decimal ',')
    "1,299.90"  -> 1299.90 (group ',', decimal '.')
"""
from __future__ import annotations

import re
from typing import Any

_CURRENCY_TOKENS = {
    "cop": "COP", "$": "COP", "colombiano": "COP",
    "usd": "USD", "u$": "USD", "dolares": "USD", "dollar": "USD",
    "eur": "EUR", "euros": "EUR", "€": "EUR",
}


def _looks_like_group_decimal(dot: int, comma: int) -> tuple[str, str]:
    """Decide group vs decimal separators from counts in a numeric string."""
    # If both present, the rightmost is the decimal separator (intl convention).
    if dot and comma:
        last_dot = dot  # placeholder
        return ("", "")
    return ("", "")


def parse_price(price_text: Any, default_currency: str = "COP") -> dict[str, Any] | None:
    """Parse a price string. Returns {'value': float|int, 'currency': str} or None."""
    if price_text is None:
        return None
    if isinstance(price_text, (int, float)):
        return {"value": float(price_text), "currency": default_currency}
    s = str(price_text).strip()
    if not s:
        return None

    # currency detection
    currency = default_currency
    low = s.lower()
    for tok, cur in _CURRENCY_TOKENS.items():
        if tok in low:
            currency = cur
            break

    # strip currency symbols / words
    cleaned = re.sub(r"[^\d.,]", "", s)
    if not cleaned:
        return None

    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        # rightmost separator is decimal
        if cleaned.rfind(",") > cleaned.rfind("."):
            # decimal comma, group dot
            num = cleaned.replace(".", "").replace(",", ".")
        else:
            # decimal dot, group comma
            num = cleaned.replace(",", "")
    elif has_dot:
        # If there's exactly one dot and <=2 digits after it -> decimal; else group sep.
        parts = cleaned.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2:
            num = cleaned
        else:
            num = cleaned.replace(".", "")
    elif has_comma:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            num = cleaned.replace(",", ".")
        else:
            num = cleaned.replace(",", "")
    else:
        num = cleaned

    try:
        value = float(num)
    except ValueError:
        return None

    # Keep integer prices as int for cleanliness
    if value.is_integer():
        value = int(value)
    return {"value": value, "currency": currency}
