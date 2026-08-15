"""Flatten canonical products into ML-ready rows.

This is DERIVED data (clearly tagged ``derived=true``). It does NOT produce
predictions or synthetic labels; it only flattens existing attributes into a
feature table suitable for later model training.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..models import CanonicalProduct


def flatten_for_ml(product: CanonicalProduct) -> dict[str, Any]:
    specs = product.specifications
    best = product.best_price
    row: dict[str, Any] = {
        "derived": True,
        "product_id": product.product_id,
        "name": product.identity.name,
        "brand": product.identity.brand,
        "category": product.identity.category,
        "subcategory": product.identity.subcategory,
        "price": best.value if best else None,
        "currency": best.currency if best else None,
        "price_cop": product.best_price_cop.value if product.best_price_cop else None,
        "availability_best": product.offers[0].availability if product.offers else "unknown",
        "num_offers": len(product.offers),
        "use_cases": "|".join(product.use_cases),
        "features": "|".join(product.features),
        # category-agnostic numeric features (nullable)
        "weight_g": specs.get("weight_g"),
        "wireless": specs.get("wireless"),
        "bluetooth": specs.get("bluetooth"),
        # mouse
        "sensor_dpi": specs.get("sensor_dpi"),
        "polling_rate_hz": specs.get("polling_rate_hz"),
        "buttons": specs.get("buttons"),
        # keyboard
        "key_count": specs.get("key_count"),
        "rgb": specs.get("rgb"),
        "backlight": specs.get("backlight"),
        "hot_swappable": specs.get("hot_swappable"),
        # headphones
        "driver_size_mm": specs.get("driver_size_mm"),
        "microphone": specs.get("microphone"),
        "active_noise_cancellation": specs.get("active_noise_cancellation"),
        "impedance_ohm": specs.get("impedance_ohm"),
        # monitor
        "screen_size_in": specs.get("screen_size_in"),
        "refresh_rate_hz": specs.get("refresh_rate_hz"),
        "response_time_ms": specs.get("response_time_ms"),
        "brightness_nits": specs.get("brightness_nits"),
        "hdr": specs.get("hdr"),
        # provenance
        "source_kind": product.source.source_kind if product.source else None,
    }
    return row


def write_ml_datasets(products: list[CanonicalProduct], out_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [flatten_for_ml(p) for p in products]

    jsonl_path = out_dir / "ml_features.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    csv_path = out_dir / "ml_features.csv"
    if rows:
        fieldnames = list(rows[0].keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: ("" if v is None else v) for k, v in r.items()})

    parquet_path: Path | None = None
    try:
        import pandas as pd  # type: ignore

        parquet_path = out_dir / "ml_features.parquet"
        pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    except Exception:  # noqa: BLE001
        # pandas/pyarrow optional; CSV+JSONL always produced
        parquet_path = None

    result = {"jsonl": jsonl_path, "csv": csv_path}
    if parquet_path:
        result["parquet"] = parquet_path
    return result
