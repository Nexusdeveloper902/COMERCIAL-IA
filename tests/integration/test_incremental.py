"""Tests for incremental shard processing + run history."""
import json
from pathlib import Path

import yaml

from commercial_ai.config import ensure_dirs
from commercial_ai.pipelines.collect import collect_raw
from commercial_ai.pipelines.normalize_pipeline import run_pipeline
from commercial_ai.scrapers import SampleSourceScraper
from commercial_ai.storage.pipeline_state import PipelineState


def _config(tmp_path: Path) -> dict:
    cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
    for k in ("raw_dir", "normalized_dir", "rejected_dir",
              "derived_dir", "interactions_dir", "logs_dir"):
        cfg["paths"][k] = str(tmp_path / cfg["paths"][k].split("/")[-1])
    cfg["paths"]["taxonomy_dir"] = "data/taxonomy"
    cfg["paths"]["sample_dir"] = "data/sample"
    cfg["paths"]["data_dir"] = str(tmp_path)
    cfg["scraping"]["cache_dir"] = str(tmp_path / "http_cache")
    cfg["pipeline"]["state_file"] = str(tmp_path / "state.json")
    ensure_dirs(cfg)
    return cfg


def test_raw_is_date_sharded(tmp_path):
    cfg = _config(tmp_path)
    state = PipelineState(cfg["pipeline"]["state_file"])
    collect_raw([SampleSourceScraper(cfg["paths"]["sample_dir"])], cfg["paths"]["raw_dir"], state)
    shards = list(Path(cfg["paths"]["raw_dir"]).glob("raw_*.jsonl"))
    assert len(shards) == 1
    assert shards[0].name.startswith("raw_") and shards[0].name.endswith(".jsonl")


def test_incremental_processing_marks_shards(tmp_path):
    cfg = _config(tmp_path)
    state = PipelineState(cfg["pipeline"]["state_file"])
    collect_raw([SampleSourceScraper(cfg["paths"]["sample_dir"])], cfg["paths"]["raw_dir"], state)

    # First run: no explicit raw_path -> processes all un-processed shards.
    stats1 = run_pipeline(cfg)
    assert stats1["raw_records"] == 6
    assert stats1["shards_processed"] == 1

    # Second run: shards now marked processed -> 0 new records.
    stats2 = run_pipeline(cfg)
    assert stats2["raw_records"] == 0
    assert stats2["shards_processed"] == 0


def test_run_history_appended(tmp_path):
    cfg = _config(tmp_path)
    state = PipelineState(cfg["pipeline"]["state_file"])
    collect_raw([SampleSourceScraper(cfg["paths"]["sample_dir"])], cfg["paths"]["raw_dir"], state)
    run_pipeline(cfg)
    run_pipeline(cfg)
    history = Path(cfg["paths"]["data_dir"]) / "run_history.jsonl"
    assert history.exists()
    lines = history.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    entries = [json.loads(l) for l in lines]
    assert "finished_at" in entries[0]
    assert "raw_records" in entries[0]
