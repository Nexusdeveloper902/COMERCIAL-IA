"""Full normalize -> validate -> dedup -> output pipeline."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..deduplication import Deduplicator
from ..derived import write_ml_datasets
from ..models import RawRecord, RejectedRecord
from ..normalization import Normalizer
from ..storage.jsonl import JsonlWriter, read_jsonl
from ..storage.pipeline_state import PipelineState
from ..taxonomy import TaxonomyLoader
from ..validation import Validator

log = logging.getLogger(__name__)

MIN_FREE_GB = 2.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / (1024 ** 3)


def _iter_raw_shards(raw_dir: Path) -> list[Path]:
    """All raw_*.jsonl shards sorted oldest-first."""
    if not raw_dir.exists():
        return []
    return sorted(raw_dir.glob("raw_*.jsonl"))


def _iter_raw_records(raw_paths: list[Path], state: PipelineState) -> Iterator[tuple[dict[str, Any], Path]]:
    """Yield (record_dict, shard_path) for records from un-processed shards only."""
    for shard in raw_paths:
        if state.is_shard_processed(shard.name):
            continue
        for rec in read_jsonl(shard):
            yield rec, shard


def run_pipeline(
    cfg: dict[str, Any],
    raw_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run normalization + validation + dedup over raw JSONL and emit outputs.

    Incremental: processes only un-processed raw shards, marking each shard done
    after it is consumed, so a crash resumes from the next shard. Pass an explicit
    ``raw_path`` to process a single file instead (used by tests / one-off runs).

    Writes a run-history entry to ``data/run_history.jsonl`` for monitoring.
    """
    paths = cfg["paths"]
    data_dir = Path(paths["data_dir"])
    raw_dir = Path(paths["raw_dir"])

    # --- disk guard ---------------------------------------------------------
    data_dir.mkdir(parents=True, exist_ok=True)
    free = _free_gb(data_dir)
    if free < MIN_FREE_GB:
        raise RuntimeError(
            f"insufficient disk space: {free:.2f} GB free < {MIN_FREE_GB} GB required"
        )

    taxonomy = TaxonomyLoader(paths["taxonomy_dir"])
    normalizer = Normalizer(taxonomy, default_currency=cfg["currency"]["default"])
    validator = Validator(taxonomy, allowed_currencies=cfg["currency"]["allowed"])

    state = PipelineState(cfg["pipeline"]["state_file"])

    # Determine which raw inputs to process.
    if raw_path is not None:
        raw_paths = [Path(raw_path)]
        single = True
    else:
        raw_paths = _iter_raw_shards(raw_dir)
        single = False

    normalized_dir = Path(paths["normalized_dir"])
    rejected_dir = Path(paths["rejected_dir"])
    derived_dir = Path(paths["derived_dir"])
    normalized_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    deduper = Deduplicator()
    rejected: list[RejectedRecord] = []
    total = 0
    valid = 0
    shards_done = 0

    rec_iter = _iter_raw_records(raw_paths, state)
    for raw_dict, shard in rec_iter:
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

    # Mark shards processed (only when iterating the raw dir, not a single file).
    if not single:
        for shard in raw_paths:
            if not state.is_shard_processed(shard.name):
                state.mark_shard_processed(shard.name, count=0)
                shards_done += 1

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
        "shards_processed": shards_done,
        "free_gb": round(free, 2),
        "outputs": {
            "raw": str(raw_paths[-1]) if raw_paths else None,
            "normalized": str(canonical_path),
            "rejected": str(rejected_path),
            "derived": {k: str(v) for k, v in ml_paths.items()},
        },
    }

    # --- run history (append, never overwrite) ------------------------------
    history_path = data_dir / "run_history.jsonl"
    entry = {"finished_at": _now(), **stats}
    with JsonlWriter(history_path) as hw:
        hw.write(entry)

    log.info("pipeline done: %s", stats)
    return stats
