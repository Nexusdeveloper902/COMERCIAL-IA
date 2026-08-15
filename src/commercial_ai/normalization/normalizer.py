"""The shared normalizer: RawRecord -> (CanonicalProduct | partial, warnings).

Normalization is a pure data transformation. It does NOT decide validity (that is
the Validator's job) and it does NOT invent missing values (None is used instead).
"""
from __future__ import annotations

import logging
from typing import Any

from ..models import (
    CanonicalProduct,
    Identifiers,
    Identity,
    Offer,
    Price,
    RawRecord,
    fingerprint,
    product_id_from_fingerprint,
)
from ..taxonomy.loader import TaxonomyLoader
from .brand import (
    detect_brand_in_text,
    infer_features,
    infer_use_cases,
    normalize_availability,
    normalize_brand,
)
from .category import infer_category, infer_subcategory
from .currency import parse_price
from .specs import SpecNormalizer

log = logging.getLogger(__name__)


class Normalizer:
    def __init__(self, taxonomy: TaxonomyLoader, default_currency: str = "COP"):
        self.taxonomy = taxonomy
        self.default_currency = default_currency
        self.spec_normalizer = SpecNormalizer(taxonomy)

    def normalize(self, raw_record: RawRecord) -> CanonicalProduct:
        raw = raw_record.raw or {}
        title = raw.get("title") or ""
        specs = raw.get("specifications") or {}
        description = raw.get("description") or ""
        price_text = raw.get("price_text")
        images = raw.get("images") or []

        # --- category / subcategory --------------------------------------
        category = raw.get("category") or infer_category(title, description)
        if category and not self.taxonomy.is_valid_category(category):
            # If inferred but not in taxonomy, fall back to None (validator will reject).
            category = None
        subcategory = infer_subcategory(category, title, description) if category else None

        # --- brand / model -----------------------------------------------
        brand = normalize_brand(raw.get("brand")) or detect_brand_in_text(title) or detect_brand_in_text(description)
        model = (raw.get("model") or self._model_from_specs(specs) or self._model_from_title(title))
        if model:
            model = str(model).strip() or None

        # --- identifiers --------------------------------------------------
        mpn = str(specs.get("Modelo") or specs.get("model") or raw.get("mpn") or "").strip() or None
        ean = str(raw.get("ean") or specs.get("EAN") or "").strip() or None
        upc = str(raw.get("upc") or specs.get("UPC") or "").strip() or None
        sku = str(raw.get("sku") or "").strip() or None

        # --- specs --------------------------------------------------------
        canonical_specs, extra_specs = self.spec_normalizer.normalize(category, specs)

        # --- price / offer -----------------------------------------------
        parsed = parse_price(price_text, self.default_currency)
        price = Price(value=(parsed["value"] if parsed else None),
                      currency=(parsed["currency"] if parsed else self.default_currency))
        availability = normalize_availability(raw.get("availability"))
        seller_name = raw.get("seller_name") or raw_record.source.domain
        seller_url = raw.get("seller_url") or raw_record.source.url

        offer = Offer(
            seller_name=str(seller_name),
            seller_url=str(seller_url),
            price=price,
            availability=availability,
            stock_quantity=raw.get("stock_quantity"),
            source=raw_record.source,
        )

        # --- use cases / features (derived from text, but explicitly tagged) ---
        use_cases = infer_use_cases(title, description, str(specs))
        # filter to taxonomy-valid
        use_cases = [u for u in use_cases if self.taxonomy.is_valid_use_case(u)]
        features = infer_features(title, description, str(specs))
        features = [f for f in features if self.taxonomy.is_valid_feature(f)]

        # --- identity / product_id ---------------------------------------
        fp = fingerprint(category, brand, model, mpn, ean, upc)
        product_id = product_id_from_fingerprint(fp) if fp else None

        identity = Identity(
            name=title.strip() or "Unknown",
            brand=brand,
            model=model,
            category=category or "",
            subcategory=subcategory,
        )

        product = CanonicalProduct(
            product_id=product_id or "",
            identity=identity,
            identifiers=Identifiers(sku=sku, ean=ean, upc=upc, mpn=mpn),
            offers=[offer],
            best_price=price if price.value is not None else None,
            description={
                "short": raw.get("short_description"),
                "full": description or None,
                "tags": list(raw.get("tags") or []),
            },
            specifications=canonical_specs,
            specifications_extra=extra_specs,
            use_cases=use_cases,
            features=features,
            media={"images": list(images)},
            source=raw_record.source,
        )
        return product

    # -- private helpers --------------------------------------------------
    @staticmethod
    def _model_from_specs(specs: dict[str, Any]) -> str | None:
        for k in ("Modelo", "model", "Model", "MPN", "Part Number"):
            v = specs.get(k)
            if v:
                return str(v).strip()
        return None

    @staticmethod
    def _model_from_title(title: str) -> str | None:
        # Heuristic: tokens that look like a model code (e.g. G502 X PLUS, 910-006765)
        import re
        m = re.search(r"\b([A-Z0-9][A-Z0-9\- ]{2,})\b", title or "")
        return m.group(1).strip() if m else None
