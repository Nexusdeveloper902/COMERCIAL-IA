"""End-to-end pipeline integration test on sample fixtures."""
import json
from pathlib import Path

import yaml

from commercial_ai.config import ensure_dirs, load_config
from commercial_ai.pipelines.collect import collect_raw
from commercial_ai.pipelines.normalize_pipeline import run_pipeline
from commercial_ai.scrapers import SampleSourceScraper
from commercial_ai.storage.pipeline_state import PipelineState


def _config(tmp_path: Path) -> dict:
    cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
    # redirect all paths into tmp so tests are hermetic
    for k in ("raw_dir", "normalized_dir", "rejected_dir",
              "derived_dir", "interactions_dir", "logs_dir"):
        cfg["paths"][k] = str(tmp_path / cfg["paths"][k].split("/")[-1])
    # keep taxonomy_dir + sample_dir pointing at the repo (read-only inputs)
    cfg["paths"]["taxonomy_dir"] = "data/taxonomy"
    cfg["paths"]["sample_dir"] = "data/sample"
    cfg["paths"]["data_dir"] = str(tmp_path)
    cfg["scraping"]["cache_dir"] = str(tmp_path / "http_cache")
    cfg["pipeline"]["state_file"] = str(tmp_path / "state.json")
    ensure_dirs(cfg)
    return cfg


def test_pipeline_end_to_end(tmp_path):
    cfg = _config(tmp_path)
    state = PipelineState(cfg["pipeline"]["state_file"])
    raw_path = collect_raw([SampleSourceScraper(cfg["paths"]["sample_dir"])], cfg["paths"]["raw_dir"], state)
    assert Path(raw_path).exists()

    stats = run_pipeline(cfg, raw_path=raw_path)
    assert stats["raw_records"] == 6
    assert stats["rejected"] == 1
    # two store-A/B records of the same mouse merge -> 4 canonical from 5 valid
    assert stats["canonical_products"] == 4
    assert stats["duplicates_merged"] == 1

    # canonical file exists and the merged mouse has 2 offers
    products = [json.loads(l) for l in open(cfg["paths"]["normalized_dir"] + "/products.jsonl")]
    mice = [p for p in products if p["identity"]["category"] == "mouse"]
    assert len(mice) == 1
    assert len(mice[0]["commerce"]["offers"]) == 2
    assert mice[0]["commerce"]["best_price"]["value"] == 459900

    # rejected file has the unparseable-price record
    rejected = [json.loads(l) for l in open(cfg["paths"]["rejected_dir"] + "/rejected_latest.jsonl")]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "invalid_price"

    # derived datasets produced
    assert (Path(cfg["paths"]["derived_dir"]) / "ml_features.jsonl").exists()
    assert (Path(cfg["paths"]["derived_dir"]) / "ml_features.csv").exists()

    # FX: every offer keeps its original price AND gains a COP conversion.
    # Pre-seed the fx cache so no network is needed.
    import json as _json
    import time as _time
    fx_cache = Path(cfg["paths"]["data_dir"]) / ".fx_cache.json"
    fx_cache.write_text(_json.dumps({
        "fetched_at": _time.time(),
        "rates": {"USD": 1.0, "COP": 4000.0, "EUR": 0.9},
    }), encoding="utf-8")

    stats2 = run_pipeline(cfg, raw_path=raw_path)
    # JsonlWriter appends; clear between runs in this test so we read only run 2.
    products2 = [_json.loads(l) for l in open(cfg["paths"]["normalized_dir"] + "/products.jsonl")]
    mice = [p for p in products2 if p["identity"]["category"] == "mouse"]
    assert len(mice) == 1
    for offer in mice[0]["commerce"]["offers"]:
        assert offer["price_cop"] is not None
        assert offer["price_cop"]["currency"] == "COP"
        # COP->COP: converted value equals original
        assert offer["price_cop"]["value"] == offer["price"]["value"]
    assert mice[0]["commerce"]["best_price_cop"]["currency"] == "COP"
    # derived ML rows include price_cop column
    ml_row = _json.loads(open(cfg["paths"]["derived_dir"] + "/ml_features.jsonl").readline())
    assert "price_cop" in ml_row
