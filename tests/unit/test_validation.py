"""Validator tests."""
from commercial_ai.models import (
    CanonicalProduct, Identifiers, Identity, Offer, Price, RawRecord, SourceRef,
)
from commercial_ai.normalization import Normalizer
from commercial_ai.validation import Validator


def _raw(price_text="$459.900", title="Mouse Logitech G502 X PLUS"):
    return RawRecord(
        source=SourceRef(url="https://x.example/p", domain="x.example",
                         scraped_at="2026-08-15T20:00:00Z", source_kind="sample"),
        raw={"title": title, "price_text": price_text,
             "specifications": {"Modelo": "910-006765"}},
    )


def test_valid_record_passes(taxonomy):
    n = Normalizer(taxonomy)
    v = Validator(taxonomy)
    product = n.normalize(_raw())
    result = v.validate(product, _raw())
    assert result.ok, result.errors


def test_invalid_price_rejected(taxonomy):
    n = Normalizer(taxonomy)
    v = Validator(taxonomy)
    product = n.normalize(_raw(price_text="Consultar"))
    result = v.validate(product, _raw(price_text="Consultar"))
    assert not result.ok
    assert any("invalid_price" in e for e in result.errors)


def test_insufficient_identity_rejected(taxonomy):
    n = Normalizer(taxonomy)
    v = Validator(taxonomy)
    # no brand recognizable, no model, no mpn -> insufficient identity
    raw = RawRecord(
        source=SourceRef(url="https://x.example/p", domain="x.example",
                         scraped_at="2026-08-15T20:00:00Z", source_kind="sample"),
        raw={"title": "Cable HDMI 2m", "price_text": "$10.000"},
    )
    product = n.normalize(raw)
    result = v.validate(product, raw)
    assert not result.ok
    assert any("insufficient_identity" in e for e in result.errors)
