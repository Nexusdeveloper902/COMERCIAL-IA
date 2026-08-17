"""Tests for build_training_example and Interaction.suitability_from_event."""
from commercial_ai.models import (
    CanonicalProduct,
    Identifiers,
    Identity,
    Offer,
    Price,
    SourceRef,
)
from commercial_ai.recommender import (
    Budget,
    Interaction,
    Requirement,
    build_training_example,
)


def _product(price_cop=459900) -> CanonicalProduct:
    return CanonicalProduct(
        product_id="mouse_d4658c5bdf388725",
        identity=Identity(name="Logitech G502 X PLUS", brand="Logitech",
                          model="910-006765", category="mouse"),
        identifiers=Identifiers(upc="09785512345", mpn="910-006765"),
        offers=[Offer(seller_name="store-a", seller_url="https://a",
                      price=Price(value=price_cop, currency="COP"),
                      availability="in_stock",
                      source=SourceRef(url="https://a", domain="a", scraped_at="2026-08-15T20:00:00Z"),
                      price_cop=Price(value=price_cop, currency="COP"))],
        best_price=Price(value=price_cop, currency="COP"),
        best_price_cop=Price(value=price_cop, currency="COP"),
        specifications={"weight_g": 106, "sensor_dpi": 25600, "polling_rate_hz": 1000},
        features=["wireless", "gaming_sensor", "rgb"],
        use_cases=["gaming", "fps"],
        source=SourceRef(url="https://a", domain="a", scraped_at="2026-08-15T20:00:00Z"),
    )


def _req() -> Requirement:
    return Requirement(
        request_id="req_001",
        raw_text="mouse gamer FPS",
        category="mouse",
        budget=Budget(max=500000, currency="COP", max_cop=500000),
        use_cases=["gaming", "fps"],
        required_features=["wireless"],
        constraints={"min_sensor_dpi": 12000, "max_weight_g": 110},
        importance={"performance": 1.0, "price": 0.8},
    )


def test_suitability_event_map():
    assert Interaction("i", "c", "p", "r", "purchase").suitability_from_event() == 1.0
    assert Interaction("i", "c", "p", "r", "add_to_cart").suitability_from_event() == 0.7
    assert Interaction("i", "c", "p", "r", "click").suitability_from_event() == 0.4
    assert Interaction("i", "c", "p", "r", "view").suitability_from_event() == 0.2
    assert Interaction("i", "c", "p", "r", "reject").suitability_from_event() == 0.0


def test_suitability_rating_wins():
    i = Interaction("i", "c", "p", "r", "rating", rating=0.85)
    assert i.suitability_from_event() == 0.85


def test_suitability_unknown_event_returns_none():
    i = Interaction("i", "c", "p", "r", "weird_event")
    assert i.suitability_from_event() is None


def test_build_training_example_structure():
    req = _req()
    prod = _product()
    inter = Interaction("int_001", "cust_42", prod.product_id, req.request_id, "purchase")
    ex = build_training_example(req, prod, inter)

    assert ex.derived is True
    assert ex.example_id.startswith("ex_")
    assert ex.request_id == "req_001"
    assert ex.product_id == "mouse_d4658c5bdf388725"
    assert ex.customer_id == "cust_42"
    assert ex.suitability == 1.0
    assert ex.label_source == "real_interaction"
    # inputs preserved
    assert ex.requirement["category"] == "mouse"
    assert ex.product["identity"]["category"] == "mouse"
    assert ex.compatibility["category_match"] is True
    assert ex.compatibility["meets_budget"] is True
    assert ex.compatibility["passes_hard_filter"] is True
    assert ex.interaction["event_type"] == "purchase"


def test_example_id_is_deterministic():
    req = _req()
    prod = _product()
    inter = Interaction("int_001", "cust_42", prod.product_id, req.request_id, "purchase")
    ex1 = build_training_example(req, prod, inter)
    ex2 = build_training_example(req, prod, inter)
    assert ex1.example_id == ex2.example_id


def test_example_id_differs_for_different_interaction():
    req = _req()
    prod = _product()
    i1 = Interaction("int_001", "c", prod.product_id, req.request_id, "purchase")
    i2 = Interaction("int_002", "c", prod.product_id, req.request_id, "click")
    assert build_training_example(req, prod, i1).example_id != build_training_example(req, prod, i2).example_id


def test_synthetic_label_is_labeled():
    """Synthetic interactions must carry label_source=synthetic (never passed as real)."""
    req = _req()
    prod = _product()
    inter = Interaction("int_s", "c", prod.product_id, req.request_id, "purchase",
                        label_source="synthetic")
    ex = build_training_example(req, prod, inter)
    assert ex.label_source == "synthetic"


def test_reject_yields_zero_suitability():
    req = _req()
    prod = _product()
    inter = Interaction("int_r", "c", prod.product_id, req.request_id, "reject")
    ex = build_training_example(req, prod, inter)
    assert ex.suitability == 0.0
