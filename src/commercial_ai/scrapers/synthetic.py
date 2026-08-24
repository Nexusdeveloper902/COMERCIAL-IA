"""Synthetic source adapter — deterministic realistic record generator.

Purpose
-------
This source lets the pipeline run end-to-end at scale (e.g. ``--max-products 10000``)
even when no real source API key is available. It produces realistic-but-fictional
product records across the four supported categories, including the *same* product
listed by several fake stores (to exercise cross-store deduplication) and a small
fraction of malformed records (to exercise validation/rejection).

Honesty (non-negotiable)
-------------------------
Every record is tagged ``source_kind="synthetic"`` and uses a ``synthetic://``
URL scheme. These are **NOT** real scraped data and must never be relabeled as
such. They exist to validate pipeline mechanics and the recommender schema at
scale while real sources are being onboarded. This is the same principle as the
existing ``sample`` source (``source_kind="sample"``), extended to scale.

Determinism
-----------
A seed makes generation reproducible: the same seed + count yields the same
catalog, so runs and tests are stable. Identifiers use hashlib (not the
process-randomized ``hash()``) for cross-run reproducibility.
"""
from __future__ import annotations

import hashlib
import logging
import random
from typing import Any, Iterator
from urllib.parse import quote

from ..models import RawRecord
from .base import BaseScraper, now_iso

log = logging.getLogger(__name__)

# Real brand + model vocabulary per category (brands are real; model strings are
# illustrative composites, not claimed to be exact real-world SKUs).
_CATALOG: dict[str, list[dict[str, Any]]] = {
    "mouse": [
        {"brand": "Logitech", "models": ["G502 X", "G Pro X Superlight 2", "G305 Lightspeed", "G203 Lightsync", "MX Master 3S"]},
        {"brand": "Razer", "models": ["DeathAdder V3 Pro", "Viper V3 Pro", "Basilisk V3", "Orochi V2"]},
        {"brand": "Corsair", "models": ["M65 RGB Ultra", "Katar Pro XT", "Sabre RGB Pro"]},
        {"brand": "SteelSeries", "models": ["Aerox 3 Wireless", "Rival 3", "Prime Wireless"]},
        {"brand": "HyperX", "models": ["Pulsefire Haste 2", "Clutch Gladiate"]},
        {"brand": "Glorious", "models": ["Model O 2", "Model D Wireless"]},
    ],
    "keyboard": [
        {"brand": "Logitech", "models": ["G915 X", "G Pro X TKL", "MX Keys S", "G715"]},
        {"brand": "Razer", "models": ["Huntsman V3 Pro", "BlackWidow V4 Pro", "DeathStalker V2"]},
        {"brand": "Corsair", "models": ["K70 RGB Pro", "K65 Mini", "Strix Scope II"]},
        {"brand": "Keychron", "models": ["Q1 Pro", "V1 Max", "K2 Pro"]},
        {"brand": "Ducky", "models": ["One 3 SF", "One 3 Mini"]},
        {"brand": "HyperX", "models": ["Alloy Origins 2", "Alloy FPS Pro"]},
    ],
    "headphones": [
        {"brand": "Sony", "models": ["WH-1000XM5", "WH-1000XM4", "WF-1000XM5"]},
        {"brand": "Bose", "models": ["QuietComfort Ultra", "QuietComfort 45", "700"]},
        {"brand": "Sennheiser", "models": ["Momentum 4", "Momentum 3", "HD 660S2"]},
        {"brand": "Audio-Technica", "models": ["ATH-M50x", "ATH-M40x"]},
        {"brand": "Razer", "models": ["BlackShark V2 Pro", "Kraken V3"]},
        {"brand": "HyperX", "models": ["Cloud III", "Cloud Alpha"]},
    ],
    "monitor": [
        {"brand": "BenQ", "models": ["Zowie XL2566K", "Zowie XL2546K", "EX3210U"]},
        {"brand": "LG", "models": ["UltraGear 27GR95QE", "UltraGear 32GP850", "UltraFine 27UP850"]},
        {"brand": "Samsung", "models": ["Odyssey G7", "Odyssey Neo G9", "Odyssey G3"]},
        {"brand": "ASUS", "models": ["ROG Swift PG27AQDM", "TUF Gaming VG279QM", "ProArt PA278CV"]},
        {"brand": "Dell", "models": ["UltraSharp U2723QE", "S2722DGM", "Alienware AW3423DW"]},
        {"brand": "MSI", "models": ["Optix MAG274QRF", "MPG321UR"]},
    ],
}

_STORES = ["tecno-store", "gaming-house", "computo-mundo", "electronica-plus"]

_USE_CASES = ["gaming", "competitive_gaming", "fps", "office", "productivity",
              "content_creation", "streaming", "programming", "music", "travel", "casual"]


def _bool_yn(rng: random.Random, p_true: float = 0.6) -> str:
    return "Sí" if rng.random() < p_true else "No"


def _mouse_specs(rng: random.Random, idx: int) -> dict[str, str]:
    return {
        "Peso": f"{rng.choice([63, 74, 85, 95, 106, 118])} g",
        "DPI": str(rng.choice([1600, 6400, 12000, 16000, 25600, 30000])),
        "Sensor": rng.choice(["óptico HERO", "óptico FocusPro", "láser", "óptico TrueMove"]),
        "Tasa de sondeo": f"{rng.choice([125, 500, 1000, 4000, 8000])} Hz",
        "Botones": str(rng.choice([2, 5, 6, 7, 8, 11, 13])),
        "Conectividad": rng.choice(["USB", "Inalámbrico 2.4 GHz", "USB / Inalámbrico 2.4 GHz"]),
        "Bluetooth": _bool_yn(rng, 0.4),
        "RGB": _bool_yn(rng, 0.7),
        "Battery life": f"{rng.choice([40, 70, 90, 120, 150, 200])} h",
    }


def _keyboard_specs(rng: random.Random, idx: int) -> dict[str, str]:
    return {
        "Layout": rng.choice(["ANSI", "ISO", "TKL ANSI", "60%"]),
        "Switch": rng.choice(["Red mecánico", "Brown táctil", "Blue clicky", "Optical Linear", "Hall Effect"]),
        "Conectividad": rng.choice(["USB-C", "Inalámbrico 2.4 GHz / USB-C", "Bluetooth / USB-C"]),
        "Bluetooth": _bool_yn(rng, 0.5),
        "RGB": _bool_yn(rng, 0.8),
        "Hot swappable": _bool_yn(rng, 0.5),
        "Teclas": str(rng.choice([61, 68, 75, 87, 104, 110])),
        "Form factor": rng.choice(["Full", "TKL", "75%", "60%"]),
    }


def _headphones_specs(rng: random.Random, idx: int) -> dict[str, str]:
    return {
        "Driver": f"{rng.choice([30, 40, 45, 50, 53])} mm",
        "Conectividad": rng.choice(["Jack 3.5", "Inalámbrico 2.4 GHz", "Bluetooth / Jack 3.5"]),
        "Bluetooth": _bool_yn(rng, 0.7),
        "Microphone": _bool_yn(rng, 0.8),
        "ANC": _bool_yn(rng, 0.5),
        "Battery life": f"{rng.choice([20, 30, 40, 50, 60])} h",
        "Peso": f"{rng.choice([180, 220, 250, 290, 340])} g",
        "Frequency response": rng.choice(["20Hz-20kHz", "5Hz-40kHz", "10Hz-30kHz"]),
        "Impedance": f"{rng.choice([16, 32, 48, 64])} ohm",
    }


def _monitor_specs(rng: random.Random, idx: int) -> dict[str, str]:
    return {
        "Tamano pantalla": f'{rng.choice([24, 24.5, 27, 32, 34, 49])} in',
        "Resolucion": rng.choice(["1920x1080", "2560x1440", "3840x2160", "3440x1440", "5120x2880"]),
        "Tasa de refresco": f"{rng.choice([60, 75, 144, 165, 240, 360, 500])} Hz",
        "Tiempo de respuesta": f"{rng.choice([0.5, 1, 2, 3, 4, 5])} ms",
        "Panel": rng.choice(["IPS", "TN", "VA", "OLED", "QD-OLED"]),
        "Brillo": f"{rng.choice([250, 300, 350, 400, 600, 1000])} nits",
        "HDR": _bool_yn(rng, 0.5),
        "Adaptive sync": _bool_yn(rng, 0.7),
        "Puertos": rng.choice(["HDMI, DisplayPort", "HDMI, DisplayPort, USB-C", "DisplayPort, USB-C"]),
    }


_SPEC_BUILDERS = {
    "mouse": _mouse_specs,
    "keyboard": _keyboard_specs,
    "headphones": _headphones_specs,
    "monitor": _monitor_specs,
}

_PRICE_BANDS = {
    "mouse": (39000, 549000),
    "keyboard": (89000, 1299000),
    "headphones": (69000, 2899000),
    "monitor": (299000, 7499000),
}


class SyntheticSourceScraper(BaseScraper):
    """Deterministic generator of realistic-but-synthetic product records.

    ``count`` records are spread across the four categories. ``dup_stores``
    controls how many stores list each product (to exercise cross-store
    deduplication). ``reject_rate`` is the fraction of deliberately-malformed
    records (to exercise validation/rejection). All output is clearly tagged
    ``source_kind="synthetic"``.
    """
    name = "synthetic"
    source_kind = "synthetic"

    def __init__(
        self,
        count: int = 1000,
        seed: int = 42,
        dup_stores: int = 2,
        reject_rate: float = 0.03,
        http_client: Any | None = None,
    ) -> None:
        super().__init__(http_client=http_client)
        self.count = max(0, count)
        self.seed = seed
        self.dup_stores = max(1, dup_stores)
        self.reject_rate = max(0.0, min(1.0, reject_rate))

    def iter_raw_records(self) -> Iterator[RawRecord]:
        if self.count == 0:
            return
        rng = random.Random(self.seed)
        categories = list(_CATALOG)
        emitted = 0
        # Systematically enumerate distinct physical products. The catalog is
        # small (~30 models/category), so we add an incrementing variant index
        # to keep generating distinct (brand, model, variant) tuples until the
        # requested count is reached. Each such tuple is ONE physical product
        # with stable mpn+ean, fanned out to ``dup_stores`` stores so cross-store
        # deduplication has real work to do.
        product_idx = 0
        while emitted < self.count:
            cat = categories[product_idx % len(categories)]
            brand_entry = rng.choice(_CATALOG[cat])
            brand = brand_entry["brand"]
            model = rng.choice(brand_entry["models"])
            # variant makes every (brand, model) repeat a NEW distinct product.
            variant = product_idx // len(categories)
            # Stable per-physical-product identifiers: same mpn+ean regardless of
            # which store lists it, so the deduper merges them into one product.
            mpn = f"{model.replace(' ', '-')}-v{variant}"
            ean = "000" + hashlib.sha1(f"{cat}|{brand}|{model}|{variant}".encode()).hexdigest()[:10]
            base_specs = _SPEC_BUILDERS[cat](rng, product_idx)
            use_cases = rng.sample(_USE_CASES, k=rng.randint(1, 3))

            n_stores = min(self.dup_stores, max(1, self.count - emitted))
            for s in range(n_stores):
                if emitted >= self.count:
                    break
                store = _STORES[(product_idx + s) % len(_STORES)]
                # Per-store price jitter so "best price" selection is exercised.
                lo, hi = _PRICE_BANDS[cat]
                base_price = rng.randint(lo, hi)
                jitter = round(base_price * rng.uniform(-0.08, 0.08))
                price_val = max(1000, base_price + jitter)
                # Colombian formatted price: dots as thousands separators.
                price_text = f"${price_val:,}".replace(",", ".")
                is_reject = rng.random() < self.reject_rate
                raw = self._build_raw(
                    cat, brand, model, mpn, ean, base_specs, use_cases, store,
                    price_text if not is_reject else "Consultar",
                    rng,
                )
                url = f"synthetic://{store}/{cat}/{quote(mpn.lower())}-{s}"
                yield self.make_raw(url, raw, scraped_at=now_iso())
                emitted += 1
            product_idx += 1
        log.info("synthetic source emitted %d records (seed=%d)", emitted, self.seed)

    def _build_raw(
        self, cat: str, brand: str, model: str, mpn: str, ean: str,
        specs: dict[str, str], use_cases: list[str], store: str,
        price_text: str, rng: random.Random,
    ) -> dict[str, Any]:
        wireless = specs.get("Bluetooth") == "Sí" or "Inalámbrico" in specs.get("Conectividad", "")
        return {
            "title": f"{brand} {model}",
            "price_text": price_text,
            "currency": "COP",
            "availability": rng.choice(["En stock", "Disponible", "Agotado", "En stock"]),
            "description": f"{cat.capitalize()} {brand} {model}. Características: " + ", ".join(use_cases) + ".",
            "short_description": f"{brand} {model}",
            "specifications": dict(specs),
            "images": [f"synthetic://img/{store}/{quote(mpn.lower())}.jpg"],
            "brand": brand,
            "model": model,
            "mpn": mpn,
            "ean": ean,
            "seller_name": store,
            "seller_url": f"https://{store}.example",
            "tags": use_cases,
        }
