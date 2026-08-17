"""CLI entry point for the COMERCIAL-IA data pipeline."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..config import ensure_dirs, load_config, setup_logging
from ..scrapers import BestBuyScraper, HttpClient, SampleSourceScraper
from .collect import collect_raw
from .normalize_pipeline import run_pipeline


def build_scrapers(cfg: dict) -> list:
    http_cfg = cfg["scraping"]
    http = HttpClient(
        cache_dir=http_cfg["cache_dir"],
        user_agent=http_cfg["user_agent"],
        rate_limit_seconds=http_cfg["rate_limit_seconds"],
        max_retries=http_cfg["max_retries"],
        backoff_base=http_cfg["backoff_base_seconds"],
        respect_robots=http_cfg["respect_robots"],
    )
    scrapers = []
    for name in cfg["pipeline"]["sources"]:
        if name == "sample":
            scrapers.append(SampleSourceScraper(sample_dir=cfg["paths"]["sample_dir"], http_client=http))
        elif name == "bestbuy":
            api_key = cfg.get("bestbuy", {}).get("api_key")
            scrapers.append(BestBuyScraper(api_key=api_key, http_client=http))
        else:
            logging.getLogger("commercial_ai").warning("unknown source '%s' (skipping)", name)
    return scrapers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="commercial-ai-pipeline")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--skip-collect", action="store_true", help="skip raw collection (reuse existing raw jsonl)")
    parser.add_argument("--raw", default=None, help="path to a raw jsonl to process (skip collect)")
    parser.add_argument("--max-products", type=int, default=None,
                        help="cap how many NEW raw records to collect this run (resumability state still preserved)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(cfg)
    ensure_dirs(cfg)

    from ..storage.pipeline_state import PipelineState

    state = PipelineState(cfg["pipeline"]["state_file"])

    if not args.skip_collect and not args.raw:
        scrapers = build_scrapers(cfg)
        collect_raw(scrapers, cfg["paths"]["raw_dir"], state, max_products=args.max_products)

    stats = run_pipeline(cfg, raw_path=args.raw)

    # Persist stats for monitoring (overwrite each run).
    stats_file = Path(cfg["paths"]["data_dir"]) / "last_run_stats.json"
    from datetime import datetime, timezone
    stats["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    stats_file.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
