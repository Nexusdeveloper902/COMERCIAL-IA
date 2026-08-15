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
- Design doc (12 deliverables): `DESIGN.md`

## Currency parsing note
Colombian format: `.`/`,` as group separators (e.g. `$499.900` = 499900 COP). When both
separators present, rightmost = decimal. See `normalization/currency.py`.

## Spanish text matching
Use accent-insensitive comparison for Spanish terms (inalámbrico etc.). Helper:
`commercial_ai.normalization.specs._deaccent`. Brand detection scans title text via
`detect_brand_in_text` (taking the first title word is unreliable — it's often a category noun).
