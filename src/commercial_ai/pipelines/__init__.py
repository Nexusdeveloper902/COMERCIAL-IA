"""Pipeline orchestration: collect -> normalize -> validate -> dedup -> output."""
from .collect import collect_raw
from .normalize_pipeline import run_pipeline

__all__ = ["collect_raw", "run_pipeline"]
