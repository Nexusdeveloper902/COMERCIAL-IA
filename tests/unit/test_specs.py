"""Spec normalization tests, incl. unknown-spec preservation."""
from commercial_ai.normalization.specs import SpecNormalizer


def test_mouse_known_specs(taxonomy):
    sn = SpecNormalizer(taxonomy)
    raw = {
        "Peso": "106 g", "DPI": "25600", "Tasa de sondeo": "1000 Hz",
        "Botones": "13", "Bluetooth": "No",
    }
    canon, extra = sn.normalize("mouse", raw)
    assert canon["weight_g"] == 106
    assert canon["sensor_dpi"] == 25600
    assert canon["polling_rate_hz"] == 1000
    assert canon["buttons"] == 13
    assert canon["bluetooth"] is False
    assert extra == {}


def test_unknown_specs_preserved(taxonomy):
    sn = SpecNormalizer(taxonomy)
    raw = {"Peso": "106 g", "RGB Zones": "2", "Custom Field": "foo"}
    canon, extra = sn.normalize("mouse", raw)
    assert canon["weight_g"] == 106
    assert extra == {"RGB Zones": "2", "Custom Field": "foo"}


def test_connectivity_split(taxonomy):
    from commercial_ai.normalization.specs import _connectivity_list
    assert _connectivity_list("USB / Inalámbrico 2.4 GHz") == ["usb", "wireless_2.4ghz"]
    assert _connectivity_list("Bluetooth") == ["bluetooth"]
    assert _connectivity_list(["HDMI", "DisplayPort"]) == ["hdmi", "displayport"]


def test_missing_value_stays_null(taxonomy):
    sn = SpecNormalizer(taxonomy)
    canon, _ = sn.normalize("mouse", {"Peso": None})
    assert canon["weight_g"] is None
