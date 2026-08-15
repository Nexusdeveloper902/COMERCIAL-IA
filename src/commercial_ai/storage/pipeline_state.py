"""Resumable pipeline state.

Tracks which URLs were already fetched and which raw records already processed,
so a crashed job resumes without re-scraping or re-processing.
State is persisted as JSON after every update.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class PipelineState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._state: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._state = {"seen_urls": {}, "processed_raw_keys": {}, "updated_at": _now()}

    def has_url(self, source: str, url: str) -> bool:
        return url in self._state["seen_urls"].get(source, {})

    def mark_url(self, source: str, url: str) -> None:
        self._state["seen_urls"].setdefault(source, {})[url] = _now()
        self._save()

    def has_raw_key(self, source: str, key: str) -> bool:
        return key in self._state["processed_raw_keys"].get(source, {})

    def mark_raw_key(self, source: str, key: str) -> None:
        self._state["processed_raw_keys"].setdefault(source, {})[key] = _now()
        self._save()

    def _save(self) -> None:
        self._state["updated_at"] = _now()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
