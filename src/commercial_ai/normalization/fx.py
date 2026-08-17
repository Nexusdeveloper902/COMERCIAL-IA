"""Currency conversion with real exchange rates (USD <-> COP).

A tiny, dependency-light converter. It fetches live rates from a free, no-API-key
endpoint (open.er-api.com, backed by ECB/forex data) and caches them on disk with
a TTL so we don't hammer the API on every run and the pipeline still works offline
when the rate service is unreachable.

Design:
* The original price is ALWAYS preserved (we never overwrite it).
* A converted ``price_cop`` is added alongside when the source price is in a
  different currency, so downstream ML can use a single comparable currency.
* If the rate fetch fails, we fall back to a configurable static rate and log a
  warning so the data is still usable (never silently invented from nothing —
  the fallback rate is explicit and logged).

Note: the well-known ``forex-python`` library was considered but its backend
(ratesapi.eu) has been unreliable and lacks COP; fetching directly from a free
no-key JSON API is simpler and more robust for Colombian Pesos.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

# Free, no API key required. Returns {"rates": {"COP": 4100.5, ...}, ...}.
DEFAULT_RATES_URL = "https://open.er-api.com/v6/latest/USD"
# Conservative fallback (updated manually if the API is down for long stretches).
DEFAULT_FALLBACK_USD_COP = 4100.0
DEFAULT_TTL_SECONDS = 24 * 3600  # refresh once per day


class CurrencyConverter:
    """Convert amounts between currencies using cached live rates.

    Base currency for rate fetch is USD (the API returns USD-denominated rates).
    COP and any other currency are derived from the USD rates table.
    """

    def __init__(
        self,
        cache_path: str | Path = "data/.fx_cache.json",
        rates_url: str = DEFAULT_RATES_URL,
        fallback_usd_cop: float = DEFAULT_FALLBACK_USD_COP,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        timeout: float = 10.0,
        user_agent: str = "commercial-ai-bot/0.1",
        respect_robots: bool = True,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.rates_url = rates_url
        self.fallback_usd_cop = fallback_usd_cop
        self.ttl = ttl_seconds
        self.timeout = timeout
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self._rates: dict[str, float] | None = None  # USD -> {cur: rate}
        self._using_fallback = False

    # -- public API --------------------------------------------------------
    def convert(self, value: float | int | None, from_currency: str, to_currency: str) -> float | None:
        """Convert ``value`` from ``from_currency`` to ``to_currency``.

        Returns None if value is None. If the currencies are equal, returns the
        value unchanged. Uses live USD rates as the pivot.
        """
        if value is None:
            return None
        src = from_currency.upper()
        dst = to_currency.upper()
        if src == dst:
            return float(value)
        rates = self._get_rates()
        # rate_usd[cur] = how many `cur` per 1 USD.
        src_to_usd = 1.0 / rates[src] if rates.get(src) else None
        dst_per_usd = rates.get(dst)
        if not src_to_usd or not dst_per_usd:
            log.warning("cannot convert %s -> %s (missing rate); src=%s dst=%s",
                        src, dst, rates.get(src), rates.get(dst))
            return None
        return round(float(value) * src_to_usd * dst_per_usd, 2)

    def is_using_fallback(self) -> bool:
        return self._using_fallback

    # -- rate loading ------------------------------------------------------
    def _get_rates(self) -> dict[str, float]:
        if self._rates is not None:
            return self._rates
        cached = self._load_cache()
        if cached and not self._is_expired(cached):
            self._rates = cached["rates"]
            log.debug("fx rates from cache (age=%.1fh)", self._age_hours(cached))
            return self._rates
        fresh = self._fetch_rates()
        if fresh:
            self._rates = fresh
            self._using_fallback = False
            self._save_cache(fresh)
            log.info("fx rates refreshed from %s (USD->COP=%s)",
                     self._domain(), fresh.get("COP"))
            return fresh
        # fall back to cache (even if expired) then static fallback
        if cached:
            self._rates = cached["rates"]
            self._using_fallback = True
            log.warning("fx fetch failed; using stale cache (USD->COP=%s)",
                        cached["rates"].get("COP"))
            return cached["rates"]
        self._rates = {"USD": 1.0, "COP": self.fallback_usd_cop}
        self._using_fallback = True
        log.warning("fx fetch failed and no cache; using static fallback USD->COP=%s",
                    self.fallback_usd_cop)
        return self._rates

    def _fetch_rates(self) -> dict[str, float] | None:
        if self.respect_robots and not self._can_fetch():
            log.info("robots.txt disallows %s; skipping fx fetch", self.rates_url)
            return None
        try:
            resp = requests.get(
                self.rates_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            rates = data.get("rates")
            if not rates or "COP" not in rates:
                log.warning("fx response missing COP rate: %s", self.rates_url)
                return None
            rates["USD"] = 1.0  # base
            return {k.upper(): float(v) for k, v in rates.items()}
        except Exception as e:  # noqa: BLE001
            log.warning("fx fetch failed: %s", e)
            return None

    # -- cache helpers -----------------------------------------------------
    def _load_cache(self) -> dict[str, Any] | None:
        if not self.cache_path.exists():
            return None
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            log.debug("fx cache load failed: %s", e)
            return None

    def _save_cache(self, rates: dict[str, float]) -> None:
        payload = {"fetched_at": time.time(), "rates": rates}
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.cache_path)

    def _is_expired(self, cached: dict[str, Any]) -> bool:
        return self._age_hours(cached) * 3600 > self.ttl

    @staticmethod
    def _age_hours(cached: dict[str, Any]) -> float:
        return (time.time() - cached.get("fetched_at", 0)) / 3600

    # -- robots ------------------------------------------------------------
    def _can_fetch(self) -> bool:
        from urllib.robotparser import RobotFileParser
        domain = self._domain()
        rp = RobotFileParser()
        robots_url = f"https://{domain}/robots.txt"
        try:
            txt = requests.get(robots_url,
                               headers={"User-Agent": self.user_agent},
                               timeout=self.timeout).text
            rp.parse(txt.splitlines())
            return rp.can_fetch(self.user_agent, self.rates_url)
        except Exception as e:  # noqa: BLE001
            log.debug("robots fetch failed for %s: %s (allowing)", domain, e)
            return True

    def _domain(self) -> str:
        return urlparse(self.rates_url).netloc


def enrich_prices_cop(
    product: Any,
    converter: "CurrencyConverter",
    target: str = "COP",
) -> None:
    """Add a ``price_cop`` (converted) to each offer in-place, preserving the
    original ``price``. Requires the offer price to have a non-None value.

    Mutates ``product.offers[*].price_cop`` in place; safe to call before dedup
    so the deduper can compare offers across different source currencies.
    """
    from ..models import Price  # local import to avoid cycle

    for offer in product.offers:
        if offer.price_cop is not None or offer.price.value is None:
            continue
        converted = converter.convert(offer.price.value, offer.price.currency, target)
        if converted is not None:
            offer.price_cop = Price(value=converted, currency=target)
