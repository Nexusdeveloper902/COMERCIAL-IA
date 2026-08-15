"""Configuration loading + structured logging setup."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def setup_logging(cfg: dict[str, Any]) -> logging.Logger:
    log_cfg = cfg.get("logging", {})
    level = getattr(logging, str(log_cfg.get("level", "INFO")).upper(), logging.INFO)
    fmt = log_cfg.get("format", "%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)
    return logging.getLogger("commercial_ai")


def ensure_dirs(cfg: dict[str, Any]) -> None:
    paths = cfg["paths"]
    for k in ("raw_dir", "normalized_dir", "rejected_dir", "taxonomy_dir",
              "derived_dir", "interactions_dir", "sample_dir", "logs_dir"):
        Path(paths[k]).mkdir(parents=True, exist_ok=True)
    Path(cfg["scraping"]["cache_dir"]).mkdir(parents=True, exist_ok=True)
