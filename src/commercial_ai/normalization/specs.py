"""Category-specific spec normalization.

Each category has a ``SpecSchema`` describing how to map raw spec values into
canonical typed fields. Unknown specs are preserved verbatim in
``specifications_extra`` (never silently dropped).
"""
from __future__ import annotations

import re
from typing import Any, Callable

from ..taxonomy.loader import TaxonomyLoader
from .numbers import extract_number, parse_bool, parse_dimensions, parse_value_with_unit


# Canonical connectivity types + aliases (mirror taxonomy/connectivity_types.json).
# Inlined here so the coercer stays self-contained; taxonomy remains the source of
# truth for membership validation.
_CANONICAL_CONN = {
    "usb", "usb_c", "wireless_2.4ghz", "bluetooth",
    "aux_3.5mm", "hdmi", "displayport", "usb_receiver",
}
_CONN_ALIASES = {
    "usb-a": "usb", "usb type-a": "usb", "usb type-c": "usb_c", "type-c": "usb_c",
    "dongle": "usb_receiver", "2.4 ghz": "wireless_2.4ghz", "2.4ghz": "wireless_2.4ghz",
    "wireless": "wireless_2.4ghz", "bt": "bluetooth", "3.5mm": "aux_3.5mm",
    "jack 3.5": "aux_3.5mm", "mini-jack": "aux_3.5mm", "dp": "displayport",
    "display port": "displayport",
}


def _connectivity_list(text: Any) -> list[str]:
    """Split a connectivity string into canonical connectivity tokens.

    e.g. "USB / Inalámbrico 2.4 GHz" -> ['usb', 'wireless_2.4ghz']
    Unknown tokens are dropped (connectivity is taxonomy-controlled).
    Accent-insensitive matching for Spanish (inalámbrico, etc.).
    """
    if text is None:
        return []
    if isinstance(text, list):
        parts = [str(t).strip() for t in text if t]
    else:
        s = str(text)
        parts = [p.strip() for p in re.split(r"[\/,]", s) if p.strip()]
    out: list[str] = []
    for p in parts:
        low = _deaccent(p.lower())
        if low in _CANONICAL_CONN:
            if low not in out:
                out.append(low)
        elif low in _CONN_ALIASES:
            c = _CONN_ALIASES[low]
            if c not in out:
                out.append(c)
        else:
            if "inalambric" in low or "wireless" in low:
                if "wireless_2.4ghz" not in out:
                    out.append("wireless_2.4ghz")
            elif "bluetooth" in low or low == "bt":
                if "bluetooth" not in out:
                    out.append("bluetooth")
            elif "usb" in low:
                if "usb" not in out:
                    out.append("usb")
    return out


def _deaccent(s: str) -> str:
    return (s.replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))


def _num(text: Any) -> float | int | None:
    return extract_number(text)


def _bool(text: Any) -> bool | None:
    return parse_bool(text)


def _dims(text: Any) -> dict[str, float | None] | None:
    return parse_dimensions(text)


# Per-category field -> coercion function.
# Fields not listed here default to raw string passthrough (then coercion attempted).
_SPEC_COERCERS: dict[str, dict[str, Callable[[Any], Any]]] = {
    "mouse": {
        "weight_g": _num,
        "sensor_dpi": _num,
        "sensor_type": lambda t: str(t).strip() if t else None,
        "polling_rate_hz": _num,
        "buttons": _num,
        "connectivity": _connectivity_list,
        "bluetooth": _bool,
        "wireless": _bool,
        "battery_life_hours": _num,
        "dimensions_mm": _dims,
    },
    "keyboard": {
        "keyboard_layout": lambda t: str(t).strip() if t else None,
        "switch_type": lambda t: str(t).strip() if t else None,
        "connectivity": _connectivity_list,
        "wireless": _bool,
        "bluetooth": _bool,
        "backlight": _bool,
        "rgb": _bool,
        "hot_swappable": _bool,
        "key_count": _num,
        "form_factor": lambda t: str(t).strip() if t else None,
        "dimensions_mm": _dims,
    },
    "headphones": {
        "driver_size_mm": _num,
        "connectivity": _connectivity_list,
        "wireless": _bool,
        "bluetooth": _bool,
        "microphone": _bool,
        "noise_cancellation": _bool,
        "active_noise_cancellation": _bool,
        "battery_life_hours": _num,
        "weight_g": _num,
        "frequency_response": lambda t: str(t).strip() if t else None,
        "impedance_ohm": _num,
    },
    "monitor": {
        "screen_size_in": _num,
        "resolution": lambda t: str(t).strip() if t else None,
        "refresh_rate_hz": _num,
        "response_time_ms": _num,
        "panel_type": lambda t: str(t).strip() if t else None,
        "aspect_ratio": lambda t: str(t).strip() if t else None,
        "brightness_nits": _num,
        "hdr": _bool,
        "adaptive_sync": lambda t: str(t).strip() if t else None,
        "ports": lambda t: t if isinstance(t, list) else ([t] if t else []),
    },
}


class SpecNormalizer:
    def __init__(self, taxonomy: TaxonomyLoader):
        self.taxonomy = taxonomy

    def normalize(self, category: str, raw_specs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (canonical_specs, extra_specs).

        Unknown raw specs (no synonym match) are placed in ``extra_specs`` verbatim.
        Known specs are coerced via the category coercer; coercion to None keeps null.
        """
        canonical: dict[str, Any] = {}
        extra: dict[str, Any] = {}

        if not raw_specs:
            return canonical, extra

        coercers = _SPEC_COERCERS.get(category, {})

        for raw_name, raw_value in raw_specs.items():
            field = self.taxonomy.resolve_spec_field(category, raw_name)
            if field is None:
                # preserve verbatim, no guessing
                extra[raw_name] = raw_value
                continue
            coercer = coercers.get(field)
            try:
                value = coercer(raw_value) if coercer else raw_value
            except Exception:  # noqa: BLE001
                value = None
            # If coercion yielded None but raw looked numeric-ish, keep null (do NOT guess).
            canonical[field] = value

        return canonical, extra
