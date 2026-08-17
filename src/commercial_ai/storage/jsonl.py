"""Incremental JSONL writer.

* Each record is one self-contained JSON line, flushed immediately, so a crash
  leaves a valid (partial) JSONL file.
* By default the file is append-only (suitable for raw collection and run
  history — true append-only logs).
* Pass ``truncate=True`` for regenerated *views* (normalized products, rejected,
  derived ML) so each run produces a fresh file rather than accumulating stale
  duplicate rows. Truncation happens atomically at open time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


class JsonlWriter:
    def __init__(self, path: str | Path, truncate: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # "a" preserves append-only semantics; truncate empties the file first.
        if truncate and self.path.exists():
            self.path.unlink()
        self._fh = open(self.path, "a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False))
        self._fh.write("\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh and not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "JsonlWriter":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)
