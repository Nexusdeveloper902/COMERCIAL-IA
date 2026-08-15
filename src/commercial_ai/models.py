"""Core data models for the COMERCIAL-IA product data pipeline.

These dataclasses define the structures that flow through the pipeline:

* ``RawRecord``          - the verbatim-ish capture from a source (raw JSONL).
* ``Offer``              - a single seller offer attached to a canonical product.
* ``CanonicalProduct``   - the normalized, validated, deduplicated product.
* ``RejectedRecord``     - a record that failed validation, kept with a reason.

All models expose ``to_dict``/``from_dict`` for JSONL (de)serialization.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively drop keys whose value is None only at leaf level is NOT done here.

    We keep None values explicitly (the spec requires null for missing values).
    This helper only normalizes dataclass outputs to plain dicts.
    """
    return d


# ---------------------------------------------------------------------------
# Raw layer
# ---------------------------------------------------------------------------


@dataclass
class SourceRef:
    url: str
    domain: str
    scraped_at: str
    source_kind: str = "scraped"  # "scraped" | "sample"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RawRecord:
    """A record as captured from a source, before any normalization."""

    source: SourceRef
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source.to_dict(), "raw": self.raw}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RawRecord":
        s = d["source"]
        return cls(
            source=SourceRef(
                url=s["url"],
                domain=s["domain"],
                scraped_at=s["scraped_at"],
                source_kind=s.get("source_kind", "scraped"),
            ),
            raw=d.get("raw", {}),
        )


# ---------------------------------------------------------------------------
# Normalized layer
# ---------------------------------------------------------------------------


@dataclass
class Price:
    value: float | int | None
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "currency": self.currency}


@dataclass
class Offer:
    """A single seller offer. A canonical product may have many offers."""

    seller_name: str
    seller_url: str
    price: Price
    availability: str  # in_stock|out_of_stock|preorder|unknown
    stock_quantity: int | None = None
    source: SourceRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seller": {"name": self.seller_name, "url": self.seller_url},
            "price": self.price.to_dict(),
            "availability": self.availability,
            "stock_quantity": self.stock_quantity,
            "source": self.source.to_dict() if self.source else None,
        }


@dataclass
class Identity:
    name: str
    brand: str | None = None
    model: str | None = None
    category: str = ""
    subcategory: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Identifiers:
    sku: str | None = None
    ean: str | None = None
    upc: str | None = None
    mpn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalProduct:
    product_id: str
    identity: Identity
    identifiers: Identifiers
    offers: list[Offer] = field(default_factory=list)
    best_price: Price | None = None
    description: dict[str, Any] = field(default_factory=dict)
    specifications: dict[str, Any] = field(default_factory=dict)
    specifications_extra: dict[str, Any] = field(default_factory=dict)
    use_cases: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    media: dict[str, Any] = field(default_factory=dict)
    source: SourceRef | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "identity": self.identity.to_dict(),
            "identifiers": self.identifiers.to_dict(),
            "commerce": {
                "offers": [o.to_dict() for o in self.offers],
                "best_price": self.best_price.to_dict() if self.best_price else None,
            },
            "description": self.description,
            "specifications": self.specifications,
            "specifications_extra": self.specifications_extra,
            "use_cases": self.use_cases,
            "features": self.features,
            "media": self.media,
            "source": self.source.to_dict() if self.source else None,
            "schema_version": self.schema_version,
        }


# ---------------------------------------------------------------------------
# Rejected layer
# ---------------------------------------------------------------------------


@dataclass
class RejectedRecord:
    reason: str
    source_record: dict[str, Any]
    validation_errors: list[str]
    fingerprint: str | None = None
    rejected_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "fingerprint": self.fingerprint,
            "source_record": self.source_record,
            "validation_errors": self.validation_errors,
            "rejected_at": self.rejected_at,
        }


# ---------------------------------------------------------------------------
# Identity fingerprint / product_id derivation (dedup key)
# ---------------------------------------------------------------------------


def _norm_token(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(str(s).lower().strip().split())


def _is_generic_model(model: str, brand: str | None) -> bool:
    """Heuristic: model strings that are too weak to safely dedup on brand+model.

    Rejects bare category nouns and very short tokens that would cause
    over-merging of unrelated products from different sources.
    """
    m = model.strip().lower()
    if not m:
        return True
    generic = {
        "mouse", "teclado", "keyboard", "monitor", "pantalla", "audifonos",
        "headphones", "headset", "auriculares", "generico", "generic",
        "cable", "usb", "hdmi", "cargador", "adapter", "mouse gaming",
    }
    if m in generic:
        return True
    # MPN-like codes contain a digit; pure letters of <=4 chars are suspect
    if not re.search(r"\d", m) and len(m) <= 4:
        return True
    return False


def fingerprint(
    category: str,
    brand: str | None,
    model: str | None,
    mpn: str | None,
    ean: str | None,
    upc: str | None,
) -> str | None:
    """Return a stable identity fingerprint, or None if identity is insufficient.

    Priority: GTIN (ean/upc) > mpn+brand > brand+model.
    The brand+model path is only used when the model is sufficiently specific
    (contains a digit / is MPN-like); generic models yield None so we do NOT
    risk over-merging unrelated products.
    """
    ean = _norm_token(ean)
    upc = _norm_token(upc)
    mpn = _norm_token(mpn)
    brand = _norm_token(brand)
    model = _norm_token(model)
    cat = _norm_token(category)

    if ean:
        key = f"gtin:{ean}"
    elif upc:
        key = f"gtin:{upc}"
    elif mpn and brand:
        key = f"mpn:{brand}:{mpn}"
    elif brand and model and not _is_generic_model(model, brand):
        key = f"bm:{brand}:{model}"
    else:
        return None  # insufficient identity -> cannot safely dedup

    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"{cat}_{h}" if cat else h


def product_id_from_fingerprint(fp: str) -> str:
    return fp
