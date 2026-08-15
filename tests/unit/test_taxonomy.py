"""Taxonomy loader tests."""
from commercial_ai.taxonomy import TaxonomyLoader


def test_categories(taxonomy):
    assert set(taxonomy.categories) == {"mouse", "keyboard", "headphones", "monitor"}


def test_valid_category(taxonomy):
    assert taxonomy.is_valid_category("mouse")
    assert not taxonomy.is_valid_category("tablet")


def test_subcategory_optional(taxonomy):
    assert taxonomy.is_valid_subcategory("mouse", None)
    assert taxonomy.is_valid_subcategory("mouse", "gaming_mouse")
    assert not taxonomy.is_valid_subcategory("mouse", "over_ear")


def test_resolve_spec_field_synonyms(taxonomy):
    assert taxonomy.resolve_spec_field("mouse", "Peso") == "weight_g"
    assert taxonomy.resolve_spec_field("mouse", "DPI") == "sensor_dpi"
    assert taxonomy.resolve_spec_field("monitor", "Tiempo de respuesta") == "response_time_ms"
    assert taxonomy.resolve_spec_field("mouse", "nonexistent_field") is None


def test_resolve_unit(taxonomy):
    assert taxonomy.resolve_unit("ms") == "ms"
    assert taxonomy.resolve_unit("hertz") == "hz"
    assert taxonomy.resolve_unit("unknown") is None


def test_resolve_connectivity(taxonomy):
    assert taxonomy.resolve_connectivity("usb") == "usb"
    assert taxonomy.resolve_connectivity("dongle") == "usb_receiver"
    assert taxonomy.resolve_connectivity("nonsense") is None
