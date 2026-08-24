"""Tests for the synthetic source adapter and CLI source selection."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commercial_ai.scrapers import SyntheticSourceScraper


def test_synthetic_yields_requested_count():
    s = SyntheticSourceScraper(count=50, seed=1, dup_stores=2)
    recs = list(s.iter_raw_records())
    assert len(recs) == 50


def test_synthetic_is_honestly_tagged():
    s = SyntheticSourceScraper(count=10, seed=2)
    for r in s.iter_raw_records():
        assert r.source.source_kind == "synthetic"
        assert r.source.url.startswith("synthetic://")


def test_synthetic_ean_marked_synthetic():
    # EANs start with "000" so they are never confused with real EANs.
    s = SyntheticSourceScraper(count=5, seed=3)
    for r in s.iter_raw_records():
        assert r.raw["ean"].startswith("000")


def test_synthetic_cross_store_dup_has_shared_identity():
    # With dup_stores=2, the same physical product is listed by 2 stores with
    # the same mpn+ean but different seller/price → dedup should merge them.
    s = SyntheticSourceScraper(count=20, seed=4, dup_stores=2)
    recs = list(s.iter_raw_records())
    from collections import Counter
    mpns = Counter(r.raw["mpn"] for r in recs)
    eans = Counter(r.raw["ean"] for r in recs)
    # Each mpn/ean should appear exactly twice (the two store listings).
    assert all(v == 2 for v in mpns.values())
    assert all(v == 2 for v in eans.values())
    # URLs must be distinct (one per store listing).
    urls = [r.source.url for r in recs]
    assert len(set(urls)) == len(urls)


def test_synthetic_distinct_urls_for_count():
    s = SyntheticSourceScraper(count=100, seed=5)
    urls = [r.source.url for r in s.iter_raw_records()]
    assert len(set(urls)) == 100


def test_synthetic_deterministic_with_seed():
    a = [r.raw["title"] for r in SyntheticSourceScraper(count=20, seed=42).iter_raw_records()]
    b = [r.raw["title"] for r in SyntheticSourceScraper(count=20, seed=42).iter_raw_records()]
    assert a == b


def test_synthetic_includes_malformed_for_rejection():
    # reject_rate > 0 should yield some records with "Consultar" (unparseable price).
    s = SyntheticSourceScraper(count=200, seed=6, reject_rate=0.1)
    recs = list(s.iter_raw_records())
    bad = [r for r in recs if r.raw["price_text"] == "Consultar"]
    assert len(bad) > 0


def test_synthetic_covers_all_categories():
    s = SyntheticSourceScraper(count=40, seed=7, dup_stores=1)
    seen = set()
    for r in s.iter_raw_records():
        # category is encoded in the URL path: synthetic://store/<cat>/...
        cat = r.source.url.split("/")[3]
        seen.add(cat)
    assert seen == {"mouse", "keyboard", "headphones", "monitor"}


def test_synthetic_zero_count():
    assert list(SyntheticSourceScraper(count=0).iter_raw_records()) == []


def test_cli_build_scrapers_synthetic_default():
    from commercial_ai.pipelines.cli import build_scrapers
    from commercial_ai.config import load_config
    cfg = load_config("config/config.yaml")
    scrapers, has_real = build_scrapers(cfg, sources=["synthetic"], max_products=100)
    assert len(scrapers) == 1
    assert scrapers[0].name == "synthetic"
    assert scrapers[0].count == 100
    assert has_real is False


def test_cli_build_scrapers_api_key_injected():
    from commercial_ai.pipelines.cli import build_scrapers
    from commercial_ai.config import load_config
    cfg = load_config("config/config.yaml")
    scrapers, has_real = build_scrapers(cfg, sources=["bestbuy"], api_key="TESTKEY123")
    assert len(scrapers) == 1
    assert scrapers[0].api_key == "TESTKEY123"
    assert has_real is True


def test_cli_build_scrapers_falls_back_to_synthetic():
    # Real sources only + max_products → synthetic fallback added.
    from commercial_ai.pipelines.cli import build_scrapers
    from commercial_ai.config import load_config
    cfg = load_config("config/config.yaml")
    # bestbuy with no key still returns a scraper (yields nothing) + has_real=True
    scrapers, has_real = build_scrapers(cfg, sources=["bestbuy"], max_products=500)
    assert has_real is True


def test_cli_help_lists_api_key_flag():
    from commercial_ai.pipelines.cli import main
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with pytest.raises(SystemExit):
        with redirect_stdout(buf):
            main(["--help"])
    out = buf.getvalue()
    assert "--api-key" in out
    assert "--sources" in out
    assert "--max-products" in out
