"""Best Buy Products API source adapter (real public data).

Uses Best Buy's public Products API (https://developer.bestbuy.com), which is a
legitimate, free, developer-facing API that returns real product data including
prices, specifications, images, SKU, and UPC. No auth bypass, no CAPTCHA, no
scraping of HTML pages — just an API key you register for free.

Setup:
  1. Register at https://developer.bestbuy.com and request a free API key.
  2. Provide the key via the env var BBY_API_KEY (preferred) or config
     ``bestbuy.api_key``. The bootstrap script injects it via a root-owned
     EnvironmentFile; never commit it to the repo.

The adapter searches for our supported categories (mouse, keyboard, headphones,
monitor) and yields raw records in the common representation. Normalization is
done separately by the shared Normalizer (source-agnostic).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterator
from urllib.parse import quote_plus

from ..models import RawRecord
from .base import BaseScraper, now_iso
from .http_client import HttpClient

log = logging.getLogger(__name__)

# Best Buy "search" category -> our internal category.
CATEGORY_QUERIES: dict[str, str] = {
    "mouse": "categoryPath.id in (abcat0205002)",
    "keyboard": "categoryPath.id in (abcat0208000)",
    "headphones": "categoryPath.id in (abcat0204000,abcat0204014)",
    "monitor": "categoryPath.id in (abcat0502000)",
}

API_BASE = "https://api.bestbuy.com/v1/products"


class BestBuyScraper(BaseScraper):
    """Real source adapter using the Best Buy Products API."""

    name = "bestbuy"
    source_kind = "scraped"

    def __init__(
        self,
        api_key: str | None = None,
        http_client: HttpClient | None = None,
        page_size: int = 25,
        max_pages: int = 20,
    ) -> None:
        super().__init__(http_client=http_client)
        self.api_key = api_key or os.environ.get("BBY_API_KEY") or ""
        if not self.api_key:
            log.warning(
                "BestBuyScraper: no API key (set BBY_API_KEY). "
                "Adapter will yield no records."
            )
        self.page_size = page_size
        self.max_pages = max_pages

    def iter_raw_records(self) -> Iterator[RawRecord]:
        if not self.api_key:
            return
        for our_category, bby_filter in CATEGORY_QUERIES.items():
            yield from self._scrape_category(our_category, bby_filter)

    def _scrape_category(self, our_category: str, bby_filter: str) -> Iterator[RawRecord]:
        for page in range(1, self.max_pages + 1):
            url = self._build_url(bby_filter, page)
            try:
                data = self.http.get_json(url) if self.http else None
            except Exception as e:  # noqa: BLE001
                log.error("bestbuy fetch failed (page %d): %s", page, e)
                break
            if not data:
                break
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                yield self._to_raw(p, our_category)
            total = data.get("total", 0)
            if page * self.page_size >= total:
                break

    def _build_url(self, bby_filter: str, page: int) -> str:
        # Best Buy v1 products search endpoint.
        return (
            f"{API_BASE}({quote_plus(bby_filter)})"
            f"?format=json&show=sku,upc,name,manufacturer,modelNumber,"
            f"regularPrice,salePrice,onSale,availability,condition,"
            f"shortDescription,longDescription,images,details,categoryPath"
            f"&pageSize={self.page_size}&page={page}&apiKey={self.api_key}"
        )

    def _to_raw(self, p: dict[str, Any], our_category: str) -> RawRecord:
        url = f"https://www.bestbuy.com/site/-/{p.get('sku')}.p"
        price = p.get("salePrice") or p.get("regularPrice")
        price_text = f"${price}" if price is not None else ""
        images = [img.get("href") for img in p.get("images", []) if img.get("href")]
        # Flatten Best Buy "details" (list of {name,value}) into a spec dict.
        specs: dict[str, str] = {}
        for d in p.get("details", []) or []:
            name = d.get("name")
            value = d.get("value")
            if name and value is not None:
                specs[name] = str(value)
        raw = {
            "title": p.get("name") or "",
            "price_text": price_text,
            "currency": "USD",
            "description": p.get("longDescription") or p.get("shortDescription") or "",
            "short_description": p.get("shortDescription") or "",
            "specifications": specs,
            "images": images,
            # Best-Buy-specific identifiers kept verbatim for normalization.
            "_bby_sku": str(p.get("sku")) if p.get("sku") else None,
            "_bby_upc": str(p.get("upc")) if p.get("upc") else None,
            "_bby_manufacturer": p.get("manufacturer"),
            "_bby_model_number": p.get("modelNumber"),
            "_bby_category_hint": our_category,
            "_bby_availability": p.get("availability"),
            "_bby_condition": p.get("condition"),
        }
        return self.make_raw(url, raw, scraped_at=now_iso())
