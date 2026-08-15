"""Fingerprint / dedup key tests."""
from commercial_ai.models import fingerprint


def test_fingerprint_from_ean():
    fp1 = fingerprint("mouse", "Logitech", "G502X", None, "1234567890123", None)
    fp2 = fingerprint("mouse", "OtherStore", "Whatever", None, "1234567890123", None)
    assert fp1 == fp2  # EAN is the strongest key -> same product


def test_fingerprint_from_mpn_brand():
    fp1 = fingerprint("mouse", "Logitech", None, "910-006765", None, None)
    fp2 = fingerprint("mouse", "logitech", "G502 X PLUS", "910-006765", None, None)
    assert fp1 == fp2  # mpn+brand match


def test_fingerprint_from_brand_model():
    fp = fingerprint("monitor", "BenQ", "XL2566K", None, None, None)
    assert fp.startswith("monitor_")


def test_fingerprint_insufficient_identity():
    assert fingerprint("mouse", None, None, None, None, None) is None
    assert fingerprint("mouse", "Logitech", None, None, None, None) is None


def test_fingerprint_rejects_generic_model():
    # "Mouse" is a bare category noun -> not safe to dedup on brand+model.
    assert fingerprint("mouse", "Logitech", "Mouse", None, None, None) is None
    assert fingerprint("keyboard", "Razer", "Teclado", None, None, None) is None
    # Very short pure-letter model -> rejected.
    assert fingerprint("monitor", "BenQ", "XL", None, None, None) is None


def test_fingerprint_accepts_specific_model():
    # Model with a digit is specific enough.
    fp = fingerprint("monitor", "BenQ", "XL2566K", None, None, None)
    assert fp is not None and fp.startswith("monitor_")
