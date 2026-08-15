# AGENTS.md — COMERCIAL-IA data project memory

Repository-specific knowledge for OpenHands agents working on this project.

## What this project is
COMERCIAL-IA product data collection & normalization system. Phase = data only
(collect → normalize → validate → dedup → ML-ready datasets). The recommendation
engine is explicitly out of scope for this phase.

## Tech & environment
- Python 3.10+ (developed on 3.13). Package installed editable: `pip install -e ".[dev,derived]"`.
- Optional `derived` extras (pandas, pyarrow) for Parquet; JSONL+CSV always produced.
- Tests: `python -m pytest tests/ -q`. Run pipeline: `python scripts/run_pipeline.py`.

## Architecture invariants (do not violate)
- Raw data is never mutated; store verbatim in `data/raw/*.jsonl`.
- Missing values → `null`. Never invent values. Unknown specs → `specifications_extra` (preserved, not dropped).
- `product_id` = deterministic identity fingerprint (EAN/UPC > MPN+brand > brand+model). NEVER use seller URL as identity.
- Single physical product sold by multiple stores → one canonical product with `commerce.offers[]` + derived `best_price`.
- Separation of concerns: scraper (fetch+extract) | normalizer (map raw→canonical) | validator (pass/reject) | deduper (merge offers) | derived (flatten for ML). Keep these in separate modules.
- Adding a source = one `BaseScraper` subclass. Adding a category = one `SpecSchema` coercer + taxonomy JSON entries.
- Scrapers respect robots.txt, rate-limit, retry w/ backoff, cache. Do NOT bypass auth/CAPTCHA/anti-bot.
- Sample fixtures (`data/sample/`) are tagged `source_kind="sample"` and are NOT real scraped data.

## Where things live
- Core models & fingerprint: `src/commercial_ai/models.py`
- Taxonomy JSON (source of truth): `data/taxonomy/*.json`; loader: `src/commercial_ai/taxonomy/loader.py`
- Normalization: `src/commercial_ai/normalization/{currency,numbers,brand,category,specs,normalizer}.py`
- Validation: `src/commercial_ai/validation/validator.py`
- Dedup: `src/commercial_ai/deduplication/deduper.py`
- Pipeline orchestration: `src/commercial_ai/pipelines/{collect,normalize_pipeline,cli}.py`
- Derived ML flattening: `src/commercial_ai/derived/ml_features.py`
- Scrapers: `src/commercial_ai/scrapers/{base,http_client,sample_source,bestbuy}.py`
- Design doc (12 deliverables): `DESIGN.md`
- Audit (pre-launch findings + Oracle recs): `AUDIT.md`
- Oracle bootstrap (rerunnable): `scripts/bootstrap_oracle.sh`

## Real source: Best Buy
- `BestBuyScraper` uses Best Buy's public Products API (free key via BBY_API_KEY env).
- Raw fields prefixed `_bby_*` (sku, upc, manufacturer, model_number, category_hint, availability).
- Normalizer maps these: `_bby_upc`→upc, `_bby_manufacturer`→brand, `_bby_model_number`→mpn/model,
  `_bby_category_hint`→category, `raw["currency"]`→price currency (USD for Best Buy).
- Config: uncomment `- bestbuy` under `pipeline.sources` in `config/config.yaml`.

## Raw processing (incremental, sharded)
- Raw files are date-sharded: `data/raw/raw_YYYYMMDD.jsonl` (NOT a single growing file).
- `PipelineState` tracks `processed_shards`; normalizer processes only un-processed shards.
- `run_pipeline(raw_path=None)` → incremental shard mode; `run_pipeline(raw_path=X)` → single file (tests).
- Disk guard: aborts if free space < 2 GB (`MIN_FREE_GB`).
- Run history appended to `data/run_history.jsonl`; latest snapshot in `data/last_run_stats.json`.

## Currency parsing note
Colombian format: `.`/`,` as group separators (e.g. `$499.900` = 499900 COP). When both
separators present, rightmost = decimal. Bare `$` is NOT mapped to any currency (ambiguous
COP/USD) — the caller's `default_currency` decides; explicit tokens (cop/usd/eur) override.
Source-supplied `raw["currency"]` (e.g. "USD" for Best Buy) wins over the config default.
See `normalization/currency.py`.

## FX conversion (USD <-> COP, real rates)
- `CurrencyConverter` in `normalization/fx.py`: fetches live rates from `open.er-api.com`
  (free, no API key, supports COP). Cached in `data/.fx_cache.json` with 24h TTL.
- If API down: stale cache -> static fallback (`fx.fallback_usd_cop`); logs `is_using_fallback`.
- Original `price` ALWAYS preserved; a derived `price_cop` is added alongside on each Offer.
- `best_price_cop` = min in-stock COP price (for cross-currency comparison).
- `enrich_prices_cop(product, converter)` mutates offers in-place; called in normalize_pipeline
  after validation, before dedup.
- ML features include both `price` (original) and `price_cop` columns.
- Why not `forex-python`: its backend (ratesapi.eu) lacks COP and is unreliable; direct
  no-key JSON API is simpler and more robust for Colombian Pesos.

## Fingerprint safety
`fingerprint()` rejects generic models (bare nouns like "Mouse"/"Teclado", short pure-letter
tokens) via `_is_generic_model()` — brand+model path only used when model has a digit.
Prevents over-merging unrelated products. Priority: GTIN (ean/upc) > mpn+brand > brand+model.

## Spanish text matching
Use accent-insensitive comparison for Spanish terms (inalámbrico etc.). Helper:
`commercial_ai.normalization.specs._deaccent`. Brand detection scans title text via
`detect_brand_in_text` (taking the first title word is unreliable — it's often a category noun).
