"""Compute Compatibility between a Requirement and a CanonicalProduct.

Pure derivation: (requirement, product) -> Compatibility. No ML, no guessing.

Constraint convention: requirement ``constraints`` keys mirror product spec names,
optionally prefixed with ``min_`` / ``max_`` to indicate direction:
  {"min_refresh_rate_hz": 144}  -> product.refresh_rate_hz >= 144 must hold
  {"max_response_time_ms": 1}   -> product.response_time_ms <= 1 must hold
A bare key (no prefix) is treated as an equality/min check depending on type.

Unknown product specs yield ``None`` (not ``False``).
"""
from __future__ import annotations

from typing import Any

from ..models import CanonicalProduct
from .models import Compatibility, Requirement


def compute_compatibility(req: Requirement, product: CanonicalProduct) -> Compatibility:
    comp = Compatibility()

    # --- category --------------------------------------------------------
    if req.category:
        comp.category_match = (product.identity.category == req.category)
    else:
        comp.category_match = None  # requirement didn't constrain category

    # --- budget ----------------------------------------------------------
    comp.meets_budget = _check_budget(req, product)

    # --- required vs preferred features ----------------------------------
    product_features = set(product.features or [])
    for f in req.required_features:
        # We can only confirm a required feature is met; we cannot know if a
        # feature is "violated" (opposite) without an explicit taxonomy of
        # antonyms, so unknown-required -> missing (not violated).
        if f in product_features:
            comp.meets_required_features.append(f)
        else:
            comp.missing_required_features.append(f)
    for f in req.preferred_features:
        comp.preferred_feature_total += 1
        if f in product_features:
            comp.preferred_feature_count += 1

    # --- use cases -------------------------------------------------------
    req_use = set(req.use_cases)
    prod_use = set(product.use_cases or [])
    comp.use_case_overlap = sorted(req_use & prod_use)

    # --- structured constraints (category-specific specs) ----------------
    specs = product.specifications or {}
    for key, threshold in req.constraints.items():
        comp.meets_constraints[key] = _check_constraint(key, threshold, specs)

    return comp


# -- helpers ------------------------------------------------------------------


def _check_budget(req: Requirement, product: CanonicalProduct) -> bool | None:
    if not req.budget:
        return None
    # Prefer the COP-converted best price for cross-currency comparison.
    price_val = None
    if product.best_price_cop and product.best_price_cop.value is not None:
        price_val = product.best_price_cop.value
    elif product.best_price and product.best_price.value is not None:
        # No COP conversion available; only usable if budget is same currency.
        if req.budget.currency == product.best_price.currency:
            price_val = product.best_price.value
    if price_val is None:
        return None  # product price unknown

    # Compare in COP when possible.
    max_cmp = req.budget.max_cop if req.budget.max_cop is not None else (
        req.budget.max if (req.budget.currency == "COP") else None
    )
    min_cmp = req.budget.min if (req.budget.currency == "COP" and req.budget.min is not None) else None

    if max_cmp is not None and price_val > max_cmp:
        return False
    if min_cmp is not None and price_val < min_cmp:
        return False
    return True


def _check_constraint(key: str, threshold: Any, specs: dict[str, Any]) -> bool | None:
    """Check a single structured constraint against product specs.

    ``min_X`` / ``max_X`` prefixes indicate direction. The base spec name ``X``
    is looked up in the product specs. Returns None if the spec is absent.
    """
    if key.startswith("min_"):
        spec_name = key[4:]
        val = _numeric(specs.get(spec_name))
        thr = _numeric(threshold)
        if val is None or thr is None:
            return None
        return val >= thr
    if key.startswith("max_"):
        spec_name = key[4:]
        val = _numeric(specs.get(spec_name))
        thr = _numeric(threshold)
        if val is None or thr is None:
            return None
        return val <= thr
    # bare key: treat numeric as min, string/bool as equality
    val = specs.get(key)
    if val is None:
        return None
    if isinstance(threshold, bool):
        return bool(val) == threshold
    if isinstance(threshold, (int, float)):
        num = _numeric(val)
        if num is None:
            return None
        return num >= threshold
    return str(val) == str(threshold)


def _numeric(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):  # guard: bool is a subclass of int
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None
