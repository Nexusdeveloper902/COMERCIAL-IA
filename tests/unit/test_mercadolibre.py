"""Tests for the Mercado Libre source adapter (raw mapping, no network)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commercial_ai.scrapers.mercadolibre import MercadoLibreScraper, _attr


def _sample_ml_result() -> dict:
    return {
        "id": "MCO123456",
        "title": "Mouse Logitech G502 Hero",
        "price": 459900,
        "currency_id": "COP",
        "permalink": "https://articulo.mercadolibre.com.co/MCO-123456-mouse-logitech-g502-_JM",
        "thumbnail": "https://http2.mlstatic.com/D_NQ_NP_thumb.jpg",
        "seller": {"nickname": "STORE_A", "permalink": "https://www.mercadolibre.com/seller"},
        "stop_time": "2026-12-31T00:00:00Z",
        "attributes": [
            {"name": "Marca", "value_name": "Logitech"},
            {"name": "Modelo", "value_name": "910-0056"},
            {"name": "DPI", "value_name": "25600"},
        ],
        "pictures": [{"url": "https://http2.mlstatic.com/D_NQ_NP_pic1.jpg"}],
    }


def test_mercadolibre_to_raw_maps_core_fields():
    s = MercadoLibreScraper()
    raw = s._to_raw(_sample_ml_result(), "mouse").raw
    assert raw["title"] == "Mouse Logitech G502 Hero"
    assert raw["price_text"] == "459900 COP"
    assert raw["currency"] == "COP"
    assert raw["brand"] == "Logitech"
    assert raw["model"] == "910-0056"
    assert raw["availability"] == "in_stock"
    assert raw["seller_name"] == "STORE_A"
    assert raw["ean"] is None
    assert raw["_ml_id"] == "MCO123456"


def test_mercadolibre_to_raw_flattens_attributes_to_specs():
    s = MercadoLibreScraper()
    raw = s._to_raw(_sample_ml_result(), "mouse").raw
    assert raw["specifications"]["Marca"] == "Logitech"
    assert raw["specifications"]["DPI"] == "25600"


def test_mercadolibre_to_raw_uses_pictures_over_thumbnail():
    s = MercadoLibreScraper()
    raw = s._to_raw(_sample_ml_result(), "mouse").raw
    assert raw["images"] == ["https://http2.mlstatic.com/D_NQ_NP_pic1.jpg"]


def test_mercadolibre_to_raw_falls_back_to_thumbnail():
    r = _sample_ml_result()
    r["pictures"] = []
    s = MercadoLibreScraper()
    raw = s._to_raw(r, "mouse").raw
    assert raw["images"] == ["https://http2.mlstatic.com/D_NQ_NP_thumb.jpg"]


def test_mercadolibre_source_url_uses_permalink():
    s = MercadoLibreScraper()
    rec = s._to_raw(_sample_ml_result(), "mouse")
    assert rec.source.url == "https://articulo.mercadolibre.com.co/MCO-123456-mouse-logitech-g502-_JM"
    assert rec.source.source_kind == "scraped"


def test_mercadolibre_build_url_paginates_with_offset():
    s = MercadoLibreScraper(page_size=50, max_pages=3)
    url0 = s._build_url("teclado", 0)
    url50 = s._build_url("teclado", 50)
    assert "offset=0" in url0
    assert "offset=50" in url50
    assert "limit=50" in url0
    assert "sites/MCO" in url0


def test_attr_helper_case_insensitive():
    assert _attr({"BRAND": "Logitech"}, "brand") == "Logitech"
    assert _attr({"marca": "Razer"}, "MARCA") == "Razer"
    assert _attr({"x": "y"}, "brand") is None
