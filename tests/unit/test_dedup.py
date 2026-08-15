"""Deduplicator tests (multi-seller offer merging)."""
from commercial_ai.models import (
    CanonicalProduct, Identifiers, Identity, Offer, Price, SourceRef,
)
from commercial_ai.deduplication import Deduplicator


def _product(pid, price, seller, url):
    return CanonicalProduct(
        product_id=pid,
        identity=Identity(name="Logitech G502 X", brand="Logitech", model="G502X", category="mouse"),
        identifiers=Identifiers(mpn="910-006765"),
        offers=[Offer(seller_name=seller, seller_url=url, price=Price(price, "COP"),
                      availability="in_stock",
                      source=SourceRef(url, "x.example", "2026-08-15T20:00:00Z", "sample"))],
        best_price=Price(price, "COP"),
    )


def test_same_id_merges_offers():
    d = Deduplicator()
    d.add(_product("mouse_abc", 459900, "Store A", "https://a.example/p"))
    d.add(_product("mouse_abc", 479900, "Store B", "https://b.example/p"))
    assert len(d.products) == 1
    assert len(d.products[0].offers) == 2
    assert d.duplicates_seen == 1
    # best price = min
    assert d.products[0].best_price.value == 459900


def test_different_ids_stay_separate():
    d = Deduplicator()
    d.add(_product("mouse_abc", 459900, "Store A", "https://a.example/p"))
    d.add(_product("mouse_xyz", 479900, "Store B", "https://b.example/p"))
    assert len(d.products) == 2


def test_identical_offer_not_duplicated():
    d = Deduplicator()
    d.add(_product("mouse_abc", 459900, "Store A", "https://a.example/p"))
    d.add(_product("mouse_abc", 459900, "Store A", "https://a.example/p"))
    assert len(d.products[0].offers) == 1
