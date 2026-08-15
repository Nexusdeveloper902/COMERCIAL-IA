"""Tests for compute_compatibility: requirement ∩ product, no invented values."""
from commercial_ai.models import (
    CanonicalProduct,
    Identifiers,
    Identity,
    Offer,
    Price,
    SourceRef,
)
from commercial_ai.recommender import Budget, Requirement, compute_compatibility


def _mouse_product(
    price_cop=459900,
    weight_g=106,
    sensor_dpi=25600,
    polling_rate_hz=1000,
    wireless=True,
    features=None,
    category="mouse",
) -> CanonicalProduct:
    return CanonicalProduct(
        product_id="mouse_d4658c5bdf388725",
        identity=Identity(name="Logitech G502 X PLUS", brand="Logitech",
                          model="910-006765", category=category),
        identifiers=Identifiers(upc="09785512345", mpn="910-006765"),
        offers=[Offer(seller_name="store-a", seller_url="https://a",
                      price=Price(value=price_cop, currency="COP"),
                      availability="in_stock",
                      source=SourceRef(url="https://a", domain="a", scraped_at="2026-08-15T20:00:00Z"),
                      price_cop=Price(value=price_cop, currency="COP"))],
        best_price=Price(value=price_cop, currency="COP"),
        best_price_cop=Price(value=price_cop, currency="COP"),
        specifications={
            "weight_g": weight_g,
            "sensor_dpi": sensor_dpi,
            "polling_rate_hz": polling_rate_hz,
            "wireless": wireless,
        },
        features=features or ["wireless", "gaming_sensor", "rgb", "lightweight"],
        use_cases=["gaming", "competitive_gaming", "fps"],
        source=SourceRef(url="https://a", domain="a", scraped_at="2026-08-15T20:00:00Z"),
    )


def _fps_req(max_cop=300000, max_weight=110, min_dpi=12000) -> Requirement:
    return Requirement(
        request_id="req_001",
        raw_text="mouse gamer inalambrico FPS",
        category="mouse",
        budget=Budget(max=300000, currency="COP", max_cop=max_cop),
        use_cases=["gaming", "competitive_gaming", "fps"],
        required_features=["wireless", "gaming_sensor"],
        preferred_features=["rgb", "lightweight"],
        constraints={
            "min_sensor_dpi": min_dpi,
            "max_weight_g": max_weight,
            "min_polling_rate_hz": 1000,
        },
        importance={"performance": 1.0, "price": 0.8},
    )


def test_category_match():
    comp = compute_compatibility(_fps_req(), _mouse_product())
    assert comp.category_match is True


def test_category_mismatch():
    comp = compute_compatibility(_fps_req(), _mouse_product(category="keyboard"))
    assert comp.category_match is False
    assert comp.passes_hard_filter is False


def test_meets_budget_when_under_max():
    # product 459900 > 300000 budget -> does NOT meet
    comp = compute_compatibility(_fps_req(max_cop=300000), _mouse_product(price_cop=459900))
    assert comp.meets_budget is False
    assert comp.passes_hard_filter is False


def test_meets_budget_when_within():
    comp = compute_compatibility(_fps_req(max_cop=500000), _mouse_product(price_cop=459900))
    assert comp.meets_budget is True


def test_required_features_met():
    comp = compute_compatibility(_fps_req(), _mouse_product())
    assert "wireless" in comp.meets_required_features
    assert "gaming_sensor" in comp.meets_required_features
    assert comp.missing_required_features == []


def test_required_feature_missing_is_not_violated():
    # use a permissive budget so only the feature logic is under test
    req = Requirement(
        request_id="r", raw_text="", category="mouse",
        required_features=["wireless", "gaming_sensor"],
        constraints={},
    )
    comp = compute_compatibility(req, _mouse_product(features=["wireless"]))
    # gaming_sensor is missing (product simply doesn't list it) -> missing, not violated
    assert "gaming_sensor" in comp.missing_required_features
    assert comp.violated_required_features == []
    # missing required feature does NOT fail the hard filter on its own
    assert comp.passes_hard_filter is True


def test_min_constraint_met():
    comp = compute_compatibility(_fps_req(min_dpi=12000), _mouse_product(sensor_dpi=25600))
    assert comp.meets_constraints["min_sensor_dpi"] is True


def test_min_constraint_violated():
    comp = compute_compatibility(_fps_req(min_dpi=30000), _mouse_product(sensor_dpi=25600))
    assert comp.meets_constraints["min_sensor_dpi"] is False
    assert comp.passes_hard_filter is False


def test_max_constraint_met():
    comp = compute_compatibility(_fps_req(max_weight=110), _mouse_product(weight_g=106))
    assert comp.meets_constraints["max_weight_g"] is True


def test_max_constraint_violated():
    comp = compute_compatibility(_fps_req(max_weight=100), _mouse_product(weight_g=106))
    assert comp.meets_constraints["max_weight_g"] is False


def test_constraint_unknown_when_spec_missing():
    """A constraint on a spec the product doesn't have -> None, not False."""
    req = Requirement(
        request_id="r", raw_text="", category="mouse",
        constraints={"min_driver_size_mm": 40},  # not a mouse spec
    )
    comp = compute_compatibility(req, _mouse_product())
    assert comp.meets_constraints["min_driver_size_mm"] is None
    # unknown constraint does NOT fail the hard filter
    assert comp.passes_hard_filter is True


def test_budget_unknown_when_product_has_no_price():
    req = Requirement(request_id="r", raw_text="", category="mouse",
                      budget=Budget(max=300000, currency="COP", max_cop=300000))
    product = _mouse_product()
    product.best_price_cop = None
    product.best_price = None
    product.offers[0].price_cop = None
    product.offers[0].price = Price(value=None, currency="COP")
    comp = compute_compatibility(req, product)
    assert comp.meets_budget is None
    assert comp.passes_hard_filter is True  # unknown budget does not fail


def test_use_case_overlap():
    comp = compute_compatibility(_fps_req(), _mouse_product())
    assert set(comp.use_case_overlap) == {"gaming", "competitive_gaming", "fps"}


def test_preferred_feature_count():
    comp = compute_compatibility(_fps_req(), _mouse_product(features=["wireless", "gaming_sensor", "rgb"]))
    # preferred = [rgb, lightweight]; only rgb present -> 1 of 2
    assert comp.preferred_feature_total == 2
    assert comp.preferred_feature_count == 1


def test_no_category_in_requirement():
    req = Requirement(request_id="r", raw_text="algo", category=None)
    comp = compute_compatibility(req, _mouse_product())
    assert comp.category_match is None
