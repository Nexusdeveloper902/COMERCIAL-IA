"""Tests for the CurrencyConverter (no real network; cache + fallback paths)."""
import json
import time

from commercial_ai.normalization.fx import CurrencyConverter


def _write_cache(tmp_path, rates, age_seconds=0):
    p = tmp_path / ".fx_cache.json"
    p.write_text(json.dumps({
        "fetched_at": time.time() - age_seconds,
        "rates": rates,
    }), encoding="utf-8")
    return p


def test_convert_same_currency_returns_value(tmp_path):
    c = CurrencyConverter(
        cache_path=tmp_path / ".fx_cache.json",
        fallback_usd_cop=4100.0,
        rates_url="http://disabled.invalid",  # won't be fetched when cache fresh
    )
    _write_cache(tmp_path, {"USD": 1.0, "COP": 4100.0})
    assert c.convert(100, "USD", "USD") == 100.0
    assert c.convert(500, "COP", "COP") == 500.0


def test_convert_usd_to_cop_from_cache(tmp_path):
    c = CurrencyConverter(cache_path=tmp_path / ".fx_cache.json")
    _write_cache(tmp_path, {"USD": 1.0, "COP": 4000.0})
    assert c.convert(100, "USD", "COP") == 400000.0
    assert not c.is_using_fallback()


def test_convert_cop_to_usd(tmp_path):
    c = CurrencyConverter(cache_path=tmp_path / ".fx_cache.json")
    _write_cache(tmp_path, {"USD": 1.0, "COP": 4000.0})
    # 400000 COP / 4000 = 100 USD
    assert c.convert(400000, "COP", "USD") == 100.0


def test_convert_none_returns_none(tmp_path):
    c = CurrencyConverter(cache_path=tmp_path / ".fx_cache.json")
    _write_cache(tmp_path, {"USD": 1.0, "COP": 4000.0})
    assert c.convert(None, "USD", "COP") is None


def test_fallback_when_no_cache_and_fetch_fails(tmp_path):
    # No cache, fetch will fail (invalid host) -> static fallback.
    c = CurrencyConverter(
        cache_path=tmp_path / ".fx_cache.json",
        rates_url="http://invalid.invalid.latest",
        fallback_usd_cop=4100.0,
        respect_robots=False,
        timeout=1.0,
    )
    assert c.convert(100, "USD", "COP") == 410000.0
    assert c.is_using_fallback()


def test_stale_cache_used_when_fetch_fails(tmp_path):
    # Cache older than TTL, fetch fails -> stale cache used (fallback=True).
    c = CurrencyConverter(
        cache_path=tmp_path / ".fx_cache.json",
        rates_url="http://invalid.invalid.latest",
        ttl_seconds=1,
        respect_robots=False,
        timeout=1.0,
    )
    _write_cache(tmp_path, {"USD": 1.0, "COP": 3900.0}, age_seconds=3600)
    assert c.convert(100, "USD", "COP") == 390000.0
    assert c.is_using_fallback()


def test_cache_not_expired_is_used_without_fetch(tmp_path):
    c = CurrencyConverter(
        cache_path=tmp_path / ".fx_cache.json",
        rates_url="http://invalid.invalid.latest",  # would fail if hit
        ttl_seconds=999999,
    )
    _write_cache(tmp_path, {"USD": 1.0, "COP": 4050.0}, age_seconds=10)
    assert c.convert(10, "USD", "COP") == 40500.0
    assert not c.is_using_fallback()
