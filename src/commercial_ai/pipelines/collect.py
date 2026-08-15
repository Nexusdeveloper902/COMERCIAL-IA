"""Raw collection stage: run scrapers, write raw JSONL incrementally."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Iterable

from ..models import RawRecord
from ..scrapers.base import BaseScraper
from ..storage.jsonl import JsonlWriter
from ..storage.pipeline_state import PipelineState

log = logging.getLogger(__name__)


def _raw_key(record: RawRecord) -> str:
    # Stable per-record key for resumability (url + title-ish).
    base = record.source.url + "|" + str(record.raw.get("title", ""))
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def collect_raw(
    scrapers: Iterable[BaseScraper],
    raw_dir: str | Path,
    state: PipelineState,
    max_products: int | None = None,
) -> Path:
    """Run all scrapers, writing raw records to a dated JSONL file.

    Resumable: already-seen URLs and already-processed raw keys are skipped.
    If ``max_products`` is set, collection stops after that many NEW records
    in this run (existing state is still preserved).
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / "raw_latest.jsonl"
    count = 0
    with JsonlWriter(out_path) as writer:
        for scraper in scrapers:
            log.info("collecting from source: %s", scraper.name)
            for record in scraper.iter_raw_records():
                if max_products is not None and max_products > 0 and count >= max_products:
                    log.info("max_products limit (%d) reached; stopping collection", max_products)
                    return out_path
                if state.has_url(scraper.name, record.source.url):
                    continue
                key = _raw_key(record)
                if state.has_raw_key(scraper.name, key):
                    continue
                writer.write(record.to_dict())
                state.mark_url(scraper.name, record.source.url)
                state.mark_raw_key(scraper.name, key)
                count += 1
    log.info("raw collection wrote %d new records to %s", count, out_path)
    return out_path
