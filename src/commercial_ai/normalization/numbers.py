"""Numeric and unit extraction."""
from __future__ import annotations

import re
from typing import Any


def extract_number(text: Any) -> float | int | None:
    """Extract the first numeric value (with optional decimal) from text."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        v = float(text)
        return int(v) if v.is_integer() else v
    s = str(text).strip()
    if not s:
        return None
    m = re.search(r"-?\d[\d.,]*", s)
    if not m:
        return None
    raw = m.group(0)
    # interpret dots as group sep if there are multiple, or as decimal if single w/ <=2 decimals
    if "." in raw and "," in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "." in raw:
        parts = raw.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2:
            pass  # decimal dot
        else:
            raw = raw.replace(".", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    try:
        v = float(raw)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def parse_value_with_unit(text: Any, expected_unit: str | None = None) -> dict[str, Any] | None:
    """Extract {'value': number, 'unit': canonical_unit} or {'value': number}.

    Examples:
        "1ms"        -> {'value': 1, 'unit': 'ms'}
        "1 ms"       -> {'value': 1, 'unit': 'ms'}
        "1000 Hz"    -> {'value': 1000, 'unit': 'hz'}
        "25600"      -> {'value': 25600}
    """
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    val = extract_number(s)
    if val is None:
        return None
    # find trailing unit token
    m = re.search(r"([a-z/²³]+)\s*$", s)
    unit = None
    if m:
        unit = m.group(1)
    if expected_unit and unit is None:
        unit = expected_unit
    out: dict[str, Any] = {"value": val}
    if unit:
        out["unit"] = unit
    return out


_BOOL_TRUE = {"si", "sí", "yes", "true", "verdadero", "1", "y", "con", "incluido"}
_BOOL_FALSE = {"no", "false", "falso", "0", "n", "sin"}


def parse_bool(text: Any) -> bool | None:
    if text is None:
        return None
    if isinstance(text, bool):
        return text
    if isinstance(text, (int, float)):
        return bool(text)
    s = str(text).strip().lower()
    if not s:
        return None
    if s in _BOOL_TRUE:
        return True
    if s in _BOOL_FALSE:
        return False
    return None


def parse_dimensions(text: Any) -> dict[str, float | None] | None:
    """Parse 'L x W x H' (mm) into {'length','width','height'}; partial ok."""
    if text is None:
        return None
    s = str(text)
    nums = re.findall(r"\d[\d.,]*", s)
    if not nums:
        return None
    parsed = [extract_number(n) for n in nums]
    keys = ["length", "width", "height"]
    return {keys[i]: (parsed[i] if i < len(parsed) else None) for i in range(3)}
