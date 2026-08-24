"""Validator: rule-based checks. Fatal failures route records to data/rejected/.

Principles:
* Validate, do NOT mutate values.
* Collect all errors (not just the first) so rejected records are self-explanatory.
* Non-fatal issues -> warnings (record may still pass).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from ..models import CanonicalProduct, RawRecord, RejectedRecord
from ..taxonomy.loader import TaxonomyLoader

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Validator:
    def __init__(self, taxonomy: TaxonomyLoader, allowed_currencies: list[str] | None = None):
        self.taxonomy = taxonomy
        self.allowed_currencies = allowed_currencies or ["COP", "USD", "EUR"]

    # -- top level ---------------------------------------------------------
    def validate(self, product: CanonicalProduct, raw_record: RawRecord) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        self._check_required(product, errors)
        self._check_category(product, errors)
        self._check_price(product, errors, warnings)
        self._check_urls(product, errors, warnings)
        self._check_numeric_specs(product, errors, warnings)
        self._check_identity(product, errors, warnings)
        self._check_source(product, errors)

        ok = not errors
        return ValidationResult(ok=ok, errors=errors, warnings=warnings)

    def reject(self, product: CanonicalProduct, raw_record: RawRecord, result: ValidationResult) -> RejectedRecord:
        reason = result.errors[0].split(":")[0].strip().replace(" ", "_").lower() if result.errors else "invalid"
        return RejectedRecord(
            reason=reason,
            source_record=raw_record.to_dict(),
            validation_errors=result.errors,
            fingerprint=product.product_id or None,
        )

    # -- checks ------------------------------------------------------------
    def _check_required(self, p: CanonicalProduct, errors: list[str]) -> None:
        if not p.identity.name or p.identity.name == "Unknown":
            errors.append("missing_name: product name is required")
        if not p.identity.category:
            errors.append("missing_category: category could not be determined")
        if not p.offers:
            errors.append("missing_offer: at least one offer is required")

    def _check_category(self, p: CanonicalProduct, errors: list[str]) -> None:
        if p.identity.category and not self.taxonomy.is_valid_category(p.identity.category):
            errors.append(f"invalid_category: {p.identity.category}")
        if p.identity.category and not self.taxonomy.is_valid_subcategory(p.identity.category, p.identity.subcategory):
            errors.append(f"invalid_subcategory: {p.identity.subcategory}")

    def _check_price(self, p: CanonicalProduct, errors: list[str], warnings: list[str]) -> None:
        for i, offer in enumerate(p.offers):
            if offer.price.value is None:
                errors.append(f"invalid_price: offer[{i}] price could not be parsed")
                continue
            if offer.price.value <= 0:
                errors.append(f"invalid_price: offer[{i}] price must be > 0")
            if offer.price.currency not in self.allowed_currencies:
                errors.append(f"invalid_currency: offer[{i}] {offer.price.currency}")

    def _check_urls(self, p: CanonicalProduct, errors: list[str], warnings: list[str]) -> None:
        for i, offer in enumerate(p.offers):
            if offer.source and not _is_url(offer.source.url):
                errors.append(f"invalid_url: offer[{i}] source url")
            if offer.seller_url and not _is_url(offer.seller_url):
                warnings.append(f"invalid_url: offer[{i}] seller url")
        for img in p.media.get("images", []):
            if not _is_url(img):
                warnings.append(f"invalid_url: image {img}")

    def _check_numeric_specs(self, p: CanonicalProduct, errors: list[str], warnings: list[str]) -> None:
        # plausible ranges: zero/negative numeric specs are suspicious
        numeric_fields = {
            "sensor_dpi": (1, 60000),
            "polling_rate_hz": (1, 8000),
            "buttons": (1, 30),
            "weight_g": (1, 5000),
            "battery_life_hours": (1, 5000),
            "key_count": (1, 200),
            "driver_size_mm": (1, 200),
            "impedance_ohm": (1, 1000),
            "screen_size_in": (1, 120),
            "refresh_rate_hz": (1, 1000),
            "response_time_ms": (0.1, 100),
            "brightness_nits": (50, 5000),
        }
        for field_name, (lo, hi) in numeric_fields.items():
            v = p.specifications.get(field_name)
            if v is None:
                continue
            if not isinstance(v, (int, float)):
                warnings.append(f"non_numeric_spec: {field_name}={v!r}")
                continue
            if v < lo or v > hi:
                warnings.append(f"out_of_range_spec: {field_name}={v} (expected {lo}..{hi})")

    def _check_identity(self, p: CanonicalProduct, errors: list[str], warnings: list[str]) -> None:
        if not p.product_id:
            errors.append("insufficient_identity: cannot compute dedup fingerprint (need ean/upc/mpn or brand+model)")

    def _check_source(self, p: CanonicalProduct, errors: list[str]) -> None:
        for offer in p.offers:
            if not offer.source or not offer.source.url or not offer.source.scraped_at:
                errors.append("missing_source_attribution: offer lacks source url/scraped_at")


def _is_url(s: Any) -> bool:
    if not s or not isinstance(s, str):
        return False
    try:
        r = urlparse(s)
        return bool(r.scheme in ("http", "https", "sample", "synthetic") and r.netloc)
    except Exception:  # noqa: BLE001
        return False
