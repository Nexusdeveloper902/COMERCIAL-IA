"""Mercado Libre public Products API source adapter (real public data).

Uses Mercado Libre's public REST API (https://developers.mercadolibre.com), which
returns real product data (title, price, currency, seller, images, attributes)
without an API key for read-only search queries. The Colombia site (``MCO``) is
used by default.

Notes
-----
* ML applies per-IP rate limiting and may return ``403 PolicyAgent`` from
  datacenter/cloud IP ranges. If you see 403s, run from a residential connection
  or register an ML application at https://developers.mercadolibre.com and pass
  an access token (the adapter falls back to authenticated requests when one is
  provided). No anti-bot/CAPTCHA bypass is performed.
* The adapter maps ML ``attributes`` into the common raw representation; the
  shared Normalizer handles normalization (source-agnostic).
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

# ML category search queries per our internal category.
CATEGORY_QUERIES: dict[str, str] = {
    "mouse": "mouse",
    "keyboard": "teclado",
    "headphones": "audifonos",
    "monitor": "monitor",
}

API_BASE = "https://api.mercadolibre.com/sites"


class MercadoLibreScraper(BaseScraper):
    """Real source adapter using the Mercado Libre public search API."""

    name = "mercadolibre"
    source_kind = "scraped"

    def __init__(
        self,
        site: str = "MCO",
        access_token: str | None = None,
        http_client: HttpClient | None = None,
        page_size: int = 50,
        max_pages: int = 20,
    ) -> None:
        super().__init__(http_client=http_client)
        self.site = site
        self.access_token = access_token or os.environ.get("ML_ACCESS_TOKEN")
        self.page_size = min(50, page_size)  # ML caps search pageSize at 50
        self.max_pages = max_pages

    def iter_raw_records(self) -> Iterator[RawRecord]:
        for our_category, query in CATEGORY_QUERIES.items():
            yield from self._scrape_category(our_category, query)

    def _scrape_category(self, our_category: str, query: str) -> Iterator[RawRecord]:
        for offset in range(0, self.page_size * self.max_pages, self.page_size):
            url = self._build_url(query, offset)
            try:
                data = self.http.get_json(url) if self.http else None
            except Exception as e:  # noqa: BLE001
                log.error("mercadolibre fetch failed (offset %d): %s", offset, e)
                break
            if not data:
                break
            results = data.get("results", [])
            if not results:
                break
            for r in results:
                yield self._to_raw(r, our_category)
            total = data.get("paging", {}).get("total", 0)
            if offset + self.page_size >= total:
                break

    def _build_url(self, query: str, offset: int) -> str:
        url = (
            f"{API_BASE}/{self.site}/search?q={quote_plus(query)}"
            f"&limit={self.page_size}&offset={offset}"
        )
        if self.access_token:
            url += f"&access_token={self.access_token}"
        return url

    def _to_raw(self, r: dict[str, Any], our_category: str) -> RawRecord:
        url = r.get("permalink") or f"https://mercadolibre.com/item/{r.get('id')}"
        price = r.get("price")
        price_text = f"{price} {r.get('currency_id', '')}".strip() if price is not None else ""
        images = []
        for pic in (r.get("pictures") or []):
            if isinstance(pic, dict) and pic.get("url"):
                images.append(pic["url"])
        if not images and r.get("thumbnail"):
            images.append(r["thumbnail"])
        # Flatten ML attributes (list of {id,name,value_name}) into a spec dict.
        specs: dict[str, str] = {}
        for attr in (r.get("attributes") or []):
            name = attr.get("name")
            value = attr.get("value_name")
            if name and value is not None:
                specs[name] = str(value)
        # Availability from ML shipping/stop_time heuristics.
        avail = "unknown"
        if r.get("stop_time"):
            avail = "in_stock"
        raw = {
            "title": r.get("title") or "",
            "price_text": price_text,
            "currency": r.get("currency_id") or "",
            "description": r.get("title") or "",
            "short_description": r.get("title") or "",
            "specifications": specs,
            "images": images,
            "brand": _attr(specs, "BRAND", "Marca"),
            "model": _attr(specs, "MODEL", "Modelo"),
            "mpn": _attr(specs, "MPN", "PartNumber") or _attr(specs, "MODEL", "Modelo"),
            "ean": _attr(specs, "EAN", "GTIN"),
            "upc": _attr(specs, "UPC"),
            "availability": avail,
            "seller_name": (r.get("seller") or {}).get("nickname") or "mercadolibre",
            "seller_url": (r.get("seller") or {}).get("permalink") or url,
            "tags": [our_category],
            "_ml_id": r.get("id"),
            "_ml_category_hint": our_category,
        }
        return self.make_raw(url, raw, scraped_at=now_iso())


def _attr(specs: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        if k in specs and specs[k]:
            return specs[k]
        kl = k.lower()
        for sk, sv in specs.items():
            if sk.lower() == kl and sv:
                return sv
    return None
