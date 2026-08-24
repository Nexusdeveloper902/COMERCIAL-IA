# COMERCIAL-IA — Product Data Collection & Normalization

A modular system to **collect, normalize, validate, and deduplicate** public
product data for an electronics store, producing **ML-ready** JSONL/Parquet/CSV
datasets that will later feed the COMERCIAL-IA recommendation engine.

> **Phase scope:** high-quality product data collection + normalization +
> validation + preparation for future ML. The recommendation engine itself is
> **out of scope** for this phase (see `DESIGN.md` §12 for the future plan).

## Data flow

```
Source Adapter  →  Raw Record  →  Raw JSONL
                                        ↓
                              Shared Normalizer
                                        ↓
                                  Validator  ──✗──→  data/rejected/*.jsonl  (+ reason)
                                        ↓
                              Deduplicator (identity fingerprint → multi-seller offers)
                                        ↓
                              Canonical Product JSONL  (data/normalized/products.jsonl)
                                        ↓
                              Derived ML datasets      (data/derived/*.parquet, *.csv, *.jsonl)
```

Originals are **never** destroyed: raw data is kept verbatim, unknown specs are
preserved in `specifications_extra`, and missing values use `null` (never guessed).

## Initial categories

`mouse`, `keyboard`, `headphones`, `monitor`. Adding a category = one new
`SpecSchema` + a taxonomy entry; nothing else changes.

## Project structure

```
commercial-ai-data/
├── src/commercial_ai/
│   ├── models.py            # RawRecord, CanonicalProduct, Offer, RejectedRecord, fingerprint
│   ├── config.py
│   ├── taxonomy/            # loader + JSON taxonomy files
│   ├── scrapers/            # BaseScraper, HttpClient (robots/retries/cache), SampleSourceScraper
│   ├── normalization/       # currency, numbers, units, brand, availability, features, specs
│   ├── validation/          # rule-based validator → pass/reject
│   ├── deduplication/       # identity fingerprint + multi-seller offer merging
│   ├── storage/             # incremental JSONL writer + resumable pipeline state
│   ├── recommender/         # training-example schema (Requirement, Interaction,
│   │                        # Compatibility, TrainingExample) — derivation only, no model
│   ├── derived/             # ML feature flattening (labeled "derived")
│   └── pipelines/           # collect + normalize_pipeline + CLI
├── data/
│   ├── raw/                 # *.jsonl (incremental, append-only)
│   ├── normalized/          # products.jsonl
│   ├── rejected/            # *.jsonl (+ reason)
│   ├── taxonomy/            # categories, subcategories, use_cases, features,
│   │                        # connectivity_types, spec_names, units, requirement_dimensions
│   ├── interactions/        # reserved for future interactions
│   ├── derived/             # ml_features.{jsonl,csv,parquet} (derived=true)
│   └── sample/              # sample fixtures + recommender/ (requirement, interaction, training_example)
├── tests/                   # unit + integration
├── scripts/run_pipeline.py
├── config/config.yaml
├── DESIGN.md                # 12 required design deliverables
├── RECOMMENDER.md           # training-example schema (Requirement + Product + Interaction -> one ML row)
├── AUDIT.md                 # pre-launch audit findings + resolutions
└── pyproject.toml
```

## Installation

```bash
pip install -e ".[dev,derived]"
```

`derived` extras (`pandas`, `pyarrow`) are optional — Parquet output is skipped
if they're absent; JSONL+CSV are always produced.

## Running the pipeline

```bash
# Default: generates a deterministic 10k-scale synthetic dataset (no key needed,
# tagged source_kind="synthetic") + full normalize/validate/dedup/FX/ML pipeline:
python scripts/run_pipeline.py --max-products 10000

# or the installed entry point:
commercial-ai-pipeline --max-products 10000

# Real Best Buy data (needs an API key — see "Sources" below):
python scripts/run_pipeline.py --sources bestbuy --api-key YOUR_BBY_KEY --max-products 10000

# Combine sources (Best Buy + Mercado Libre), falling back to synthetic if
# the real sources yield nothing in this environment:
python scripts/run_pipeline.py --sources bestbuy,mercadolibre --api-key YOUR_BBY_KEY --max-products 10000

# 0 = unlimited:
python scripts/run_pipeline.py --max-products 0
# reuse existing raw jsonl without re-scraping:
python scripts/run_pipeline.py --skip-collect
# change the synthetic generator seed for a different (still reproducible) catalog:
python scripts/run_pipeline.py --max-products 10000 --seed 99
```

**Flags:**
- `--max-products N` — cap new raw records this run (with the default `synthetic` source, this many are generated). Resumability state is still preserved.
- `--sources a,b,c` — comma-separated source list: `synthetic`, `sample`, `bestbuy`, `mercadolibre`. Default: `config/config.yaml` `pipeline.sources` (currently `synthetic`).
- `--api-key KEY` — Best Buy API key, injected without touching config/env files.
- `--seed N` — seed for the synthetic generator (default 42).

Outputs are written under `data/` and a stats summary is printed. Each run also
appends an entry to `data/run_history.jsonl` (never overwritten) and writes a
latest snapshot to `data/last_run_stats.json` for monitoring.

### Sources

| source | needs key? | notes |
|---|---|---|
| `synthetic` (default) | no | deterministic realistic generator; 10k-scale; `source_kind="synthetic"`. Lets the pipeline run end-to-end immediately. **NOT real data** — never relabel it. |
| `sample` | no | offline fixtures from `data/sample/*.json`; `source_kind="sample"`. |
| `bestbuy` | **yes** (`--api-key` or `BBY_API_KEY`) | real Best Buy Products API. Register at https://developer.bestbuy.com. **Note:** Best Buy rejects free-email domains (Gmail/Yahoo/Outlook) at signup — use a non-free address. Caps: 100/page × 200 pages = up to 20k records. |
| `mercadolibre` | no (read-only) | real ML public API (site `MCO` = Colombia). ML blocks datacenter IPs (`403 PolicyAgent`); run from a residential connection or register an app at https://developers.mercadolibre.com and set `ML_ACCESS_TOKEN`. |

If you configure only real sources (`bestbuy`/`mercadolibre`) with `--max-products`
but they can't produce data here (no key / datacenter IP), the pipeline automatically
adds the `synthetic` source so you still get a dataset — clearly tagged `synthetic`.

### Raw processing is incremental

Raw files are **date-sharded** (`data/raw/raw_YYYYMMDD.jsonl`) so they stay
bounded. The normalizer processes only **un-processed shards**, marking each
done in `data/.pipeline_state.json`, so a crash resumes from the next shard
without re-processing. A disk-space guard aborts the run if free space drops
below 2 GB.

## Key guarantees

- **Honest provenance:** every record carries `source.{url,domain,scraped_at,source_kind}`.
- **Original prices preserved:** a USD Best Buy offer keeps `price: {value:149.99, currency:USD}`
  and also gains `price_cop: {value:..., currency:COP}` converted from real exchange rates.
  The bundled `SampleSourceScraper` reads `data/sample/*.json` fixtures tagged
  `source_kind="sample"` — these exercise the pipeline but are **never** presented
  as real scraped data. Real sources are added by implementing one `BaseScraper` subclass.
- **No invented values:** missing → `null`; unknown specs preserved in `specifications_extra`.
- **Crash-safe & resumable:** raw records written incrementally (line-buffered);
  `data/.pipeline_state.json` tracks seen URLs/keys so jobs resume without re-scraping.
- **Scraping safety:** respects `robots.txt`, rate-limits, exponential-backoff
  retries, on-disk HTTP cache. Does **not** bypass auth/CAPTCHA/anti-bot.
- **Identity-based dedup:** `product_id` is a deterministic hash of manufacturer
  identifiers (EAN/UPC > MPN+brand > brand+model), never a seller URL. The same
  physical product sold by several stores becomes one canonical product with
  multiple `commerce.offers`.

## Adding a new source

1. Subclass `BaseScraper` (mix in `HttpClient` for HTTP sources).
2. Implement `iter_raw_records()` to fetch + extract source-specific fields into
   the common raw representation `{ source: {...}, raw: { title, price_text, ... } }`.
3. Register it in `config/config.yaml` under `pipeline.sources`.

Normalization, validation, and dedup are source-agnostic and shared.

### Real source: Best Buy Products API

`BestBuyScraper` (`src/commercial_ai/scrapers/bestbuy.py`) uses Best Buy's public
[Products API](https://developer.bestbuy.com) — a free, developer-facing API
returning real product data (prices, specs, UPC, manufacturer, model). It is a
legitimate API (no HTML scraping, no auth/CAPTCHA bypass).

To enable it:
1. Register at <https://developer.bestbuy.com> and get a free API key.
2. Provide the key via the env var `BBY_API_KEY` (preferred — the Oracle
   bootstrap script injects it via a root-owned `EnvironmentFile=`), or set
   `bestbuy.api_key` in `config/config.yaml` for local dev (never commit it).
3. Uncomment `- bestbuy` under `pipeline.sources` in `config/config.yaml`.

The adapter searches Best Buy's categories for our four product types, paginates
through results, and yields raw records. The shared normalizer maps Best Buy
fields (`_bby_upc` → `upc`, `_bby_manufacturer` → `brand`, `currency: USD`, etc.).

## Currency conversion (real USD ↔ COP rates)

The pipeline converts every offer price to Colombian Pesos using **real, live
exchange rates**, while **keeping the original price untouched**. So a Best Buy
USD offer ends up as:

```json
"offers": [{
  "price":      {"value": 149.99, "currency": "USD"},
  "price_cop":  {"value": 599996.0, "currency": "COP"}
}]
```

How it works (`src/commercial_ai/normalization/fx.py`):
- Fetches rates from a **free, no-API-key** endpoint (`open.er-api.com`, which
  supports COP — `forex-python`'s backend lacks COP and has been unreliable).
- Rates are cached on disk (`data/.fx_cache.json`) with a 24h TTL, so repeated
  runs don't hammer the API.
- If the API is unreachable, it falls back to a stale cache, then a static
  configurable rate (`fx.fallback_usd_cop` in config) — and logs that it's using
  a fallback so the data provenance stays honest.
- `best_price_cop` is computed per product (min in-stock COP price) so the
  recommender can compare products across USD and COP sources on one scale.
- The derived ML dataset includes both `price` (original) and `price_cop` columns.

Config (`config/config.yaml`):
```yaml
fx:
  rates_url: "https://open.er-api.com/v6/latest/USD"
  fallback_usd_cop: 4100.0
  ttl_seconds: 86400
```

## Adding a new category

1. Add the category to `data/taxonomy/categories.json`.
2. Add subcategories + spec synonyms to the relevant taxonomy JSON files.
3. Add a `SpecSchema` coercer entry in `src/commercial_ai/normalization/specs.py`.

## Tests

```bash
python -m pytest tests/ -q
```

## Future ML integration

The schema preserves attributes destined to become features (price, category,
use_cases, weight, connectivity, performance specs, feature availability). The
future pipeline is:

```
Customer → LLM → Structured Requirements → Candidate Filtering
→ ML Recommendation/Ranking → Top Products → LLM Explanation → Customer
```

No ML predictions are generated in this phase. See `DESIGN.md` §12 and `RECOMMENDER.md`
for the locked-down training-example schema (`Requirement + Product + Interaction ->
TrainingExample`), which tells us exactly what behavioral data to collect next.
