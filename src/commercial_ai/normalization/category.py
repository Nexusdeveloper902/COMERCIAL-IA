"""Category inference from text (scrapers may pass an explicit category too)."""
from __future__ import annotations

import re
from typing import Any

_CATEGORY_RULES = [
    ("mouse", re.compile(r"\b(mouse|raton|ratón)\b", re.I)),
    ("keyboard", re.compile(r"\b(keyboard|teclado)\b", re.I)),
    ("headphones", re.compile(r"\b(headphone|headset|auriculares|cascos|audifonos)\b", re.I)),
    ("monitor", re.compile(r"\b(monitor|pantalla|display)\b", re.I)),
]


def infer_category(*texts: Any) -> str | None:
    blob = " ".join(str(t) for t in texts if t)
    for cat, pat in _CATEGORY_RULES:
        if pat.search(blob):
            return cat
    return None


_SUBCATEGORY_RULES = {
    "mouse": [("gaming_mouse", re.compile(r"\b(gamer|gaming|fps)\b", re.I))],
    "keyboard": [
        ("mechanical_keyboard", re.compile(r"\b(mecanic|mechanical)\b", re.I)),
        ("gaming_keyboard", re.compile(r"\b(gamer|gaming)\b", re.I)),
    ],
    "headphones": [
        ("gaming_headset", re.compile(r"\b(gamer|gaming|headset)\b", re.I)),
        ("over_ear", re.compile(r"\b(over.?ear|circumaural)\b", re.I)),
        ("in_ear", re.compile(r"\b(in.?ear|intrauditivo)\b", re.I)),
        ("true_wireless", re.compile(r"\b(true wireless|tw|tws)\b", re.I)),
    ],
    "monitor": [
        ("gaming_monitor", re.compile(r"\b(gamer|gaming|144hz|240hz|360hz|1ms|0\.5ms)\b", re.I)),
        ("professional_monitor", re.compile(r"\b(professional|pro |color accuracy|reference)\b", re.I)),
    ],
}


def infer_subcategory(category: str, *texts: Any) -> str | None:
    rules = _SUBCATEGORY_RULES.get(category, [])
    if not rules:
        return None
    blob = " ".join(str(t) for t in texts if t)
    for sub, pat in rules:
        if pat.search(blob):
            return sub
    return None
