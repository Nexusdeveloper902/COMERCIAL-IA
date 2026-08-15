"""Brand, availability, features, use-case, connectivity, category normalization."""
from __future__ import annotations

import re
from typing import Any

# Known brand synonyms -> canonical
_BRAND_SYNONYMS = {
    "logi": "Logitech",
    "logitech": "Logitech",
    "razer": "Razer",
    "corsair": "Corsair",
    "steelseries": "SteelSeries",
    "hyperx": "HyperX",
    "asus": "ASUS",
    "rog": "ASUS ROG",
    "samsung": "Samsung",
    "lg": "LG",
    "benq": "BenQ",
    "zowie": "Zowie",
    "apple": "Apple",
    "microsoft": "Microsoft",
    "hp": "HP",
    "dell": "Dell",
    "acer": "Acer",
    "msi": "MSI",
    "gigabyte": "Gigabyte",
    "aoc": "AOC",
    "philips": "Philips",
    "viewsonic": "ViewSonic",
    "sennheiser": "Sennheiser",
    "sony": "Sony",
    "bose": "Bose",
    "jbl": "JBL",
    "akg": "AKG",
    "beyerdynamic": "Beyerdynamic",
    "audio-technica": "Audio-Technica",
    "audiotechnica": "Audio-Technica",
    "kraken": "Razer Kraken",
    "redragon": "Redragon",
    "cougar": "Cougar",
    "coolermaster": "Cooler Master",
    "cooler master": "Cooler Master",
}


def normalize_brand(brand: Any) -> str | None:
    if not brand:
        return None
    s = str(brand).strip()
    low = s.lower()
    if low in _BRAND_SYNONYMS:
        return _BRAND_SYNONYMS[low]
    # Title-case unknown brands but preserve all-caps acronyms (<=4 chars)
    if s.isupper() and len(s) <= 4:
        return s
    return s.title()


def detect_brand_in_text(text: Any) -> str | None:
    """Scan text for any known brand synonym (word-boundary match).

    More robust than taking the first title word, which is often a category
    noun ('Mouse', 'Monitor', 'Teclado').
    """
    if not text:
        return None
    s = str(text)
    low = s.lower()
    # Order by length desc so 'cooler master' matches before 'cooler'
    for syn in sorted(_BRAND_SYNONYMS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(syn) + r"\b", low):
            return _BRAND_SYNONYMS[syn]
    return None


_AVAIL_MAP = [
    (re.compile(r"\b(en stock|in stock|disponible|available|en almacen)\b", re.I), "in_stock"),
    (re.compile(r"\b(agotado|out of stock|sin stock|no disponible|sold out)\b", re.I), "out_of_stock"),
    (re.compile(r"\b(preorder|pre-orden|pre orden|reserva)\b", re.I), "preorder"),
]


def normalize_availability(text: Any) -> str:
    if not text:
        return "unknown"
    s = str(text)
    for pat, val in _AVAIL_MAP:
        if pat.search(s):
            return val
    return "unknown"


# Use-case keyword rules (map free text -> taxonomy use cases)
_USE_CASE_RULES = [
    ("competitive_gaming", re.compile(r"\b(competitivo|esports|e-?sports|fps competitivo)\b", re.I)),
    ("fps", re.compile(r"\b(fps|shooter|tiro|first person)\b", re.I)),
    ("moba", re.compile(r"\b(moba|dota|league of legends|lol)\b", re.I)),
    ("gaming", re.compile(r"\b(gamer|gaming|juegos|videojuego)\b", re.I)),
    ("office", re.compile(r"\b(oficina|office|trabajo|empresarial)\b", re.I)),
    ("productivity", re.compile(r"\b(productividad|productivity)\b", re.I)),
    ("content_creation", re.compile(r"\b(creacion de contenido|content creation|edicion|edit)\b", re.I)),
    ("streaming", re.compile(r"\b(stream|streaming|twitch)\b", re.I)),
    ("programming", re.compile(r"\b(programar|programacion|programming|developer|codigo)\b", re.I)),
    ("music", re.compile(r"\b(musica|music|audiofilo|audiophile)\b", re.I)),
    ("travel", re.compile(r"\b(viaje|travel|portatil|portable)\b", re.I)),
    ("video_editing", re.compile(r"\b(edicion de video|video editing|4k edit)\b", re.I)),
    ("photo_editing", re.compile(r"\b(fotografia|photo editing|edicion de foto|color accuracy)\b", re.I)),
    ("casual", re.compile(r"\b(casual|basico|everyday|diario)\b", re.I)),
]


def infer_use_cases(*texts: Any) -> list[str]:
    blob = " ".join(str(t) for t in texts if t)
    found: list[str] = []
    for uc, pat in _USE_CASE_RULES:
        if pat.search(blob) and uc not in found:
            found.append(uc)
    return found


# Feature keyword rules -> taxonomy features
_FEATURE_RULES = [
    ("wireless", re.compile(r"\b(inalambric|wireless|sin cable)\b", re.I)),
    ("wired", re.compile(r"\b(cableado|wired|con cable)\b", re.I)),
    ("rgb", re.compile(r"\brgb\b", re.I)),
    ("backlight", re.compile(r"\b(retroiluminad|backlight|iluminad)\b", re.I)),
    ("hot_swappable", re.compile(r"\b(hot.?swap|hot swappable)\b", re.I)),
    ("programmable_buttons", re.compile(r"\b(programmable|programable|macro button|botones programable)\b", re.I)),
    ("macro_keys", re.compile(r"\b(macro key|teclas macro|macro)\b", re.I)),
    ("noise_cancellation", re.compile(r"\b(noise cancel|cancelacion de ruido|noise isolat)\b", re.I)),
    ("active_noise_cancellation", re.compile(r"\b(\banc\b|active noise cancel|cancelacion activa)\b", re.I)),
    ("microphone", re.compile(r"\b(microfono|microphone|mic\b|boom)\b", re.I)),
    ("mechanicalSwitches", re.compile(r"\b(mecanic|mechanical switch)\b", re.I)),
    ("ergonomic", re.compile(r"\b(ergonomic|ergonom)\b", re.I)),
    ("lightweight", re.compile(r"\b(ligero|ultraligero|lightweight|light weight)\b", re.I)),
    ("hdr", re.compile(r"\bhdr\b", re.I)),
    ("curved", re.compile(r"\b(curvo|curved)\b", re.I)),
    ("mechanicalSwitches", None),  # placeholder removed below
]
# remove None placeholders
_FEATURE_RULES = [(f, p) for f, p in _FEATURE_RULES if p is not None]


def infer_features(*texts: Any) -> list[str]:
    blob = " ".join(str(t) for t in texts if t)
    found: list[str] = []
    for feat, pat in _FEATURE_RULES:
        if feat in found:
            continue
        if pat.search(blob):
            found.append(feat)
    return found
