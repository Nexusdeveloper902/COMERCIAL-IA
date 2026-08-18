"""CLI entry point for the COMERCIAL-IA data pipeline."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..config import ensure_dirs, load_config, setup_logging
from ..scrapers import (
    BestBuyScraper,
    HttpClient,
    MercadoLibreScraper,
    SampleSourceScraper,
    SyntheticSourceScraper,
)
from .collect import collect_raw
from .normalize_pipeline import run_pipeline

# Sources that require real credentials/network and may yield zero records in
# this environment (BBY needs a registered key; ML 403s datacenter IPs).
_REAL_SOURCES = {"bestbuy", "mercadolibre"}


def build_scrapers(cfg: dict, sources: list[str] | None = None,
                   api_key: str | None = None, seed: int = 42,
                   max_products: int | None = None) -> list:
    http_cfg = cfg["scraping"]
    http = HttpClient(
        cache_dir=http_cfg["cache_dir"],
        user_agent=http_cfg["user_agent"],
        rate_limit_seconds=http_cfg["rate_limit_seconds"],
        max_retries=http_cfg["max_retries"],
        backoff_base=http_cfg["backoff_base_seconds"],
        respect_robots=http_cfg["respect_robots"],
    )
    active = sources if sources is not None else cfg["pipeline"]["sources"]
    scrapers = []
    has_real = False
    # When the synthetic source is used with --max-products, generate that many
    # records (default count otherwise).
    synth_count = max_products if (max_products and max_products > 0) else None
    for name in active:
        if name == "sample":
            scrapers.append(SampleSourceScraper(sample_dir=cfg["paths"]["sample_dir"], http_client=http))
        elif name == "synthetic":
            scrapers.append(SyntheticSourceScraper(count=synth_count, http_client=http, seed=seed))
        elif name == "bestbuy":
            key = api_key or cfg.get("bestbuy", {}).get("api_key")
            scrapers.append(BestBuyScraper(api_key=key, http_client=http))
            has_real = True
        elif name == "mercadolibre":
            scrapers.append(MercadoLibreScraper(http_client=http))
            has_real = True
        else:
            logging.getLogger("commercial_ai").warning("unknown source '%s' (skipping)", name)
    return scrapers, has_real


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="commercial-ai-pipeline",
        description="Collect + normalize + validate + dedup electronics product data.",
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--sources", default=None,
                        help="comma-separated source list, e.g. 'bestbuy,mercadolibre'. "
                             "Default: config pipeline.sources. Use 'synthetic' for a "
                             "deterministic 10k-scale generator (no key needed).")
    parser.add_argument("--api-key", default=None,
                        help="Best Buy API key (injected without touching config/env). "
                             "Register at https://developer.bestbuy.com")
    parser.add_argument("--seed", type=int, default=42, help="seed for the synthetic source")
    parser.add_argument("--skip-collect", action="store_true", help="skip raw collection (reuse existing raw jsonl)")
    parser.add_argument("--raw", default=None, help="path to a raw jsonl to process (skip collect)")
    parser.add_argument("--max-products", type=int, default=None,
                        help="cap how many NEW raw records to collect this run "
                             "(e.g. 10000). With the synthetic source this many "
                             "records are generated; resumability state is still preserved.")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(cfg)
    ensure_dirs(cfg)

    from ..storage.pipeline_state import PipelineState

    state = PipelineState(cfg["pipeline"]["state_file"])

    if not args.skip_collect and not args.raw:
        sources = args.sources.split(",") if args.sources else None
        scrapers, has_real = build_scrapers(
            cfg, sources=sources, api_key=args.api_key, seed=args.seed,
            max_products=args.max_products,
        )

        # If only real sources are configured but none can produce data here
        # (no key / datacenter IP), fall back to synthetic so the pipeline still
        # produces a dataset — clearly tagged source_kind="synthetic".
        if has_real and not any(s.name not in _REAL_SOURCES for s in scrapers):
            max_p = args.max_products or 0
            if max_p:
                log = logging.getLogger("commercial_ai")
                log.warning(
                    "real source(s) configured but likely unavailable here "
                    "(no BBY key / ML blocks datacenter IPs). Adding 'synthetic' "
                    "so --max-products %d still produces a dataset (tagged synthetic).",
                    max_p,
                )
                scrapers.append(SyntheticSourceScraper(count=max_p, seed=args.seed))

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
