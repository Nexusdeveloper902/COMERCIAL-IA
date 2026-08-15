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
│   ├── derived/             # ML feature flattening (labeled "derived")
│   └── pipelines/           # collect + normalize_pipeline + CLI
├── data/
│   ├── raw/                 # *.jsonl (incremental, append-only)
│   ├── normalized/          # products.jsonl
│   ├── rejected/            # *.jsonl (+ reason)
│   ├── taxonomy/            # categories, subcategories, use_cases, features,
│   │                        # connectivity_types, spec_names, units
│   ├── interactions/        # reserved for future interactions
│   ├── derived/             # ml_features.{jsonl,csv,parquet} (derived=true)
│   └── sample/              # clearly-labeled sample fixtures (NOT real scraped data)
├── tests/                   # unit + integration
├── scripts/run_pipeline.py
├── config/config.yaml
├── DESIGN.md                # 12 required design deliverables
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
python scripts/run_pipeline.py
# or
commercial-ai-pipeline
# reuse existing raw jsonl without re-scraping:
python scripts/run_pipeline.py --skip-collect
```

Outputs are written under `data/` and a stats summary is printed.

## Key guarantees

- **Honest provenance:** every record carries `source.{url,domain,scraped_at,source_kind}`.
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

No ML predictions are generated in this phase. See `DESIGN.md` §12.
