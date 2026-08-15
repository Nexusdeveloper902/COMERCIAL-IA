"""Base scraper interface.

Each source adapter is responsible for downloading/fetching data and extracting
source-specific fields into a common raw representation. Normalization happens
separately (in ``commercial_ai.normalization``).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Iterator
from urllib.parse import urlparse

from ..models import RawRecord, SourceRef

log = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class BaseScraper(ABC):
    """Abstract source adapter.

    Subclasses set ``name`` and implement ``iter_raw_records``.
    Source-specific fetching helpers (HTTP, JSON API) are mixed in as needed.
    """

    name: str = "base"
    source_kind: str = "scraped"  # "scraped" | "sample"

    def __init__(self, http_client: Any | None = None) -> None:
        self.http = http_client

    @abstractmethod
    def iter_raw_records(self) -> Iterator[RawRecord]:
        """Yield raw records (verbatim-ish capture from the source)."""
        ...

    # -- helpers shared by concrete scrapers -------------------------------
    def make_source(self, url: str, scraped_at: str | None = None) -> SourceRef:
        return SourceRef(
            url=url,
            domain=urlparse(url).netloc,
            scraped_at=scraped_at or now_iso(),
            source_kind=self.source_kind,
        )

    def make_raw(self, url: str, raw: dict[str, Any], scraped_at: str | None = None) -> RawRecord:
        return RawRecord(source=self.make_source(url, scraped_at), raw=raw)
