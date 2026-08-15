"""End-to-end normalization of a Best Buy raw record."""
from commercial_ai.models import RawRecord, SourceRef
from commercial_ai.normalization import Normalizer
from commercial_ai.validation import Validator


def _bby_raw():
    return RawRecord(
        source=SourceRef(url="https://www.bestbuy.com/site/-/6471234.p",
                         domain="www.bestbuy.com",
                         scraped_at="2026-08-15T20:00:00Z",
                         source_kind="scraped"),
        raw={
            "title": "Logitech - G502 X PLUS LIGHTSPEED Wireless Optical Gaming Mouse",
            "price_text": "$149.99",
            "currency": "USD",
            "description": "High performance wireless gaming mouse with HERO sensor.",
            "short_description": "Wireless gaming mouse",
            "specifications": {"Weight": "106 g", "DPI": "25600"},
            "images": ["https://images.example/img.jpg"],
            "_bby_sku": "6471234",
            "_bby_upc": "09785512345",
            "_bby_manufacturer": "Logitech",
            "_bby_model_number": "910-006765",
            "_bby_category_hint": "mouse",
            "_bby_availability": "Available",
            "_bby_condition": "New",
        },
    )


def test_bestbuy_normalizes_to_usd(taxonomy):
    n = Normalizer(taxonomy, default_currency="COP")
    product = n.normalize(_bby_raw())
    # currency should be USD from raw["currency"], not the COP default
    assert product.offers[0].price.currency == "USD"
    assert product.offers[0].price.value == 149.99
    assert product.offers[0].availability == "in_stock"
    # brand from _bby_manufacturer
    assert product.identity.brand == "Logitech"
    assert product.identity.category == "mouse"
    # identifiers from _bby_* fields
    assert product.identifiers.upc == "09785512345"
    assert product.identifiers.sku == "6471234"
    assert product.identifiers.mpn == "910-006765"
    # identity fingerprint uses UPC (gtin) -> stable product_id
    assert product.product_id.startswith("mouse_")
    # specs normalized
    assert product.specifications["weight_g"] == 106
    assert product.specifications["sensor_dpi"] == 25600


def test_bestbuy_record_passes_validation(taxonomy):
    n = Normalizer(taxonomy, default_currency="COP")
    v = Validator(taxonomy, allowed_currencies=["COP", "USD", "EUR"])
    raw = _bby_raw()
    product = n.normalize(raw)
    result = v.validate(product, raw)
    assert result.ok, result.errors
