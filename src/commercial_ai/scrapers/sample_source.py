"""Sample source adapter.

Reads clearly-labeled sample fixtures from ``data/sample/*.json`` to exercise the
full pipeline end-to-end without scraping real websites.

IMPORTANT: these records are tagged ``source_kind="sample"``. They are NOT
presented as real scraped data. They exist purely to validate the pipeline
mechanics and as templates for future real source adapters.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from ..models import RawRecord
from .base import BaseScraper, now_iso

log = logging.getLogger(__name__)


class SampleSourceScraper(BaseScraper):
    name = "sample"
    source_kind = "sample"

    def __init__(self, sample_dir: str | Path = "data/sample", http_client: Any | None = None) -> None:
        super().__init__(http_client=http_client)
        self.sample_dir = Path(sample_dir)

    def iter_raw_records(self) -> Iterator[RawRecord]:
        if not self.sample_dir.exists():
            log.warning("sample dir not found: %s", self.sample_dir)
            return
        for fp in sorted(self.sample_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                log.error("failed to load sample fixture %s: %s", fp, e)
                continue
            for item in data.get("records", []):
                url = item.get("source", {}).get("url", f"sample://{fp.name}")
                scraped_at = item.get("source", {}).get("scraped_at") or now_iso()
                yield self.make_raw(url, item.get("raw", {}), scraped_at=scraped_at)
