"""Full normalize -> validate -> dedup -> output pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..deduplication import Deduplicator
from ..derived import write_ml_datasets
from ..models import RawRecord, RejectedRecord
from ..normalization import Normalizer
from ..storage.jsonl import JsonlWriter, read_jsonl
from ..storage.pipeline_state import PipelineState
from ..taxonomy import TaxonomyLoader
from ..validation import Validator

log = logging.getLogger(__name__)


def run_pipeline(
    cfg: dict[str, Any],
    raw_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run normalization + validation + dedup over raw JSONL and emit outputs.

    Returns a small stats dict.
    """
    paths = cfg["paths"]
    taxonomy = TaxonomyLoader(paths["taxonomy_dir"])
    normalizer = Normalizer(taxonomy, default_currency=cfg["currency"]["default"])
    validator = Validator(taxonomy, allowed_currencies=cfg["currency"]["allowed"])

    raw_path = Path(raw_path or (Path(paths["raw_dir"]) / "raw_latest.jsonl"))
    state = PipelineState(cfg["pipeline"]["state_file"])

    normalized_dir = Path(paths["normalized_dir"])
    rejected_dir = Path(paths["rejected_dir"])
    derived_dir = Path(paths["derived_dir"])
    normalized_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    deduper = Deduplicator()
    rejected: list[RejectedRecord] = []
    total = 0
    valid = 0

    # Normalized accepted stream (post-dedup) written at the end for atomicity of
    # the canonical product list; rejected are written incrementally.
    for raw_dict in read_jsonl(raw_path):
        total += 1
        raw_record = RawRecord.from_dict(raw_dict)
        try:
            product = normalizer.normalize(raw_record)
        except Exception as e:  # noqa: BLE001
            log.error("normalization failed for %s: %s", raw_record.source.url, e)
            rejected.append(RejectedRecord(
                reason="normalization_error",
                source_record=raw_record.to_dict(),
                validation_errors=[str(e)],
            ))
            continue

        result = validator.validate(product, raw_record)
        if not result.ok:
            rejected.append(validator.reject(product, raw_record, result))
            continue
        if result.warnings:
            log.debug("warnings for %s: %s", product.product_id, result.warnings)
        deduper.add(product)
        valid += 1

    # Write rejected incrementally-style (single file, but one record per line)
    rejected_path = rejected_dir / "rejected_latest.jsonl"
    with JsonlWriter(rejected_path) as w:
        for r in rejected:
            w.write(r.to_dict())

    # Write canonical products
    products = deduper.products
    canonical_path = normalized_dir / "products.jsonl"
    with JsonlWriter(canonical_path) as w:
        for p in products:
            w.write(p.to_dict())

    # Derived ML datasets
    ml_paths = write_ml_datasets(products, derived_dir)

    stats = {
        "raw_records": total,
        "valid_normalized": valid,
        "rejected": len(rejected),
        "canonical_products": len(products),
        "duplicates_merged": deduper.duplicates_seen,
        "outputs": {
            "raw": str(raw_path),
            "normalized": str(canonical_path),
            "rejected": str(rejected_path),
            "derived": {k: str(v) for k, v in ml_paths.items()},
        },
    }
    log.info("pipeline done: %s", stats)
    return stats
