"""Deduplicator.

Merges CanonicalProducts sharing the same ``product_id`` (identity fingerprint)
into a single product whose ``commerce.offers`` aggregates every seller offer.
``best_price`` is recomputed as the minimum in-stock price (or overall min).
"""
from __future__ import annotations

import logging
from typing import Any

from ..models import CanonicalProduct, Offer, Price

log = logging.getLogger(__name__)


class Deduplicator:
    def __init__(self) -> None:
        self._by_id: dict[str, CanonicalProduct] = {}
        self._duplicates_seen: int = 0

    @property
    def products(self) -> list[CanonicalProduct]:
        return list(self._by_id.values())

    @property
    def duplicates_seen(self) -> int:
        return self._duplicates_seen

    def add(self, product: CanonicalProduct) -> CanonicalProduct:
        if not product.product_id:
            # Should not reach here (validator rejects insufficient identity),
            # but guard regardless: keep as-is under a synthetic key.
            log.warning("product without product_id reached deduper: %s", product.identity.name)
            return product

        existing = self._by_id.get(product.product_id)
        if existing is None:
            self._by_id[product.product_id] = product
            return product

        self._duplicates_seen += 1
        self._merge(existing, product)
        return existing

    def _merge(self, base: CanonicalProduct, other: CanonicalProduct) -> None:
        # merge offers (dedupe identical seller+price+source)
        for offer in other.offers:
            if not _offer_exists(base.offers, offer):
                base.offers.append(offer)

        # merge textual fields (prefer non-null, keep longest description)
        if not base.description.get("full") and other.description.get("full"):
            base.description["full"] = other.description["full"]
        if not base.description.get("short") and other.description.get("short"):
            base.description["short"] = other.description["short"]

        # merge tags / use_cases / features (union)
        base.description["tags"] = _union(base.description.get("tags", []), other.description.get("tags", []))
        base.use_cases = _union(base.use_cases, other.use_cases)
        base.features = _union(base.features, other.features)

        # merge specs (fill missing fields from other; never overwrite a present value)
        for k, v in other.specifications.items():
            if k not in base.specifications or base.specifications[k] is None:
                base.specifications[k] = v
        for k, v in other.specifications_extra.items():
            if k not in base.specifications_extra:
                base.specifications_extra[k] = v

        # merge identifiers (fill missing)
        for f in ("sku", "ean", "upc", "mpn"):
            cur = getattr(base.identifiers, f)
            other_val = getattr(other.identifiers, f)
            if not cur and other_val:
                setattr(base.identifiers, f, other_val)

        # merge media
        base.media["images"] = _union(base.media.get("images", []), other.media.get("images", []))

        # recompute best price (original currency + COP)
        base.best_price = _compute_best_price(base.offers)
        base.best_price_cop = _compute_best_price_cop(base.offers)


def _offer_exists(offers: list[Offer], offer: Offer) -> bool:
    for o in offers:
        if (o.seller_name == offer.seller_name
                and o.price.value == offer.price.value
                and o.source and offer.source and o.source.url == offer.source.url):
            return True
    return False


def _union(a: list[Any], b: list[Any]) -> list[Any]:
    out = list(a)
    for x in b:
        if x not in out:
            out.append(x)
    return out


def _compute_best_price(offers: list[Offer]) -> Price | None:
    """Best price in original currency (first offer's currency wins for tie-break).

    For cross-currency offers prefer the COP-converted value when available so
    comparisons are meaningful (a $150 USD offer is not "cheaper" than a $499900
    COP offer by raw number).
    """
    priced = [o for o in offers if o.price.value is not None]
    in_stock = [o for o in priced if o.availability == "in_stock"]
    pool = in_stock or priced
    if not pool:
        return None
    best = min(pool, key=lambda o: (o.price_cop.value if o.price_cop else o.price.value))  # type: ignore[arg-type]
    return Price(value=best.price.value, currency=best.price.currency)


def _compute_best_price_cop(offers: list[Offer]) -> Price | None:
    """Best price expressed in COP (converted). None if no offer has a COP price."""
    cop_priced = [o for o in offers if o.price_cop and o.price_cop.value is not None]
    in_stock = [o for o in cop_priced if o.availability == "in_stock"]
    pool = in_stock or cop_priced
    if not pool:
        return None
    best = min(pool, key=lambda o: o.price_cop.value)  # type: ignore[arg-type]
    return Price(value=best.price_cop.value, currency="COP")
