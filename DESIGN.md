# COMERCIAL-IA — Product Data Collection & Normalization: Design

> Phase scope: **high-quality product data collection + normalization + validation +
> preparation for future ML.** The recommendation engine itself is explicitly out of scope.

This document delivers the 12 required design artifacts and records the contradictions
that were resolved before implementation.

---

## 1. Proposed architecture

### 1.1 Core data flow (immutable, append-friendly)

```text
Fuente externa
      │
      ▼
Source Adapter  (download/fetch + source-specific extraction)
      │
      ▼
Raw Record      (verbatim-ish capture, never reinterpreted at this stage)
      │
      ▼
Raw JSONL        data/raw/<source>_<date>.jsonl   (incremental, resumable)
      │
      ▼
Shared Normalizer (currency, numbers, units, brand, availability,
                   features, category-specific specs, taxonomy mapping)
      │
      ▼
Validator       (required fields, category, price, currency, URLs,
                 numeric specs, units, duplicate hints, source attribution)
      │      ┌────────────────────────────────────────────┐
      │      │ invalid → data/rejected/*.jsonl + reason    │
      ▼      └────────────────────────────────────────────┘
Deduplicator    (identity fingerprint → merge multi-seller offers)
      │
      ▼
Canonical Product JSONL   data/normalized/products.jsonl
      │
      ▼
Derived / ML-ready         data/derived/*.parquet, *.csv   (labeled "derived")
```

### 1.2 Separation of concerns (mandatory)

| Layer        | Responsibility                                           | Must NOT do                         |
|--------------|----------------------------------------------------------|-------------------------------------|
| Source Adapter | fetch + extract source-specific fields → raw record     | normalize, validate, dedup          |
| Normalizer   | map raw → canonical, taxonomy mapping, unit/currency    | fetch, decide validity, drop unknowns |
| Validator    | rule-based checks → pass/reject                          | mutate values, invent values        |
| Deduplicator | identity-based merge of offers                           | alter source attribution            |
| Derived      | flatten for ML (clearly labeled)                         | produce predictions/scores          |

### 1.3 Modularity

```text
BaseScraper (ABC)
    ├── HttpMixin   (retries w/ exp backoff, rate limit, robots.txt, cache)
    ├── SampleSourceScraper   (offline, clearly-labeled sample fixtures)
    └── <FutureSourceScraper> (one file per source; no rewrite needed)
```

Adding a source = one new module implementing `BaseScraper` + registering it.
Adding a category = one new `SpecSchema` + a taxonomy entry; nothing else changes.

### 1.4 Crash-safety / overnight cloud execution

- Raw records are written **incrementally** to JSONL (line-buffered flush), never held only in RAM.
- A `pipeline_state.json` records seen URLs / processed record ids so the job **resumes** without re-scraping.
- Network failures recovered via retries + resumable state.
- Partial JSONL remains valid (each line is a self-contained JSON object).
- All actions logged (structured) to `logs/`.

### 1.5 Honesty about data provenance

Per the hard constraint "do NOT create a fake dataset presented as real":

- Each record carries `source.domain`, `source.url`, `source.scraped_at`.
- The bundled `SampleSourceScraper` reads **clearly-labeled sample fixtures** (in `tests/fixtures/` / `data/sample/`) and tags records with `source.source_kind = "sample"`. These exercise the pipeline end-to-end but are **never** presented as real scraped data.
- Real source adapters can be added later by dropping in a new `BaseScraper` subclass.

---

## 2. Final Product JSON schema (canonical)

Conceptual structure preserved from the brief, with one reconciled change:
`commerce` is modeled as an **offers array** so a single physical product sold by several
stores becomes one canonical product with multiple seller offers (see §5).

```jsonc
{
  "product_id": "mouse_logitech_g502x_plus",   // deterministic internal id (see §5)
  "identity": {
    "name": "Logitech G502 X PLUS",
    "brand": "Logitech",
    "model": "G502 X PLUS",
    "category": "mouse",
    "subcategory": "gaming_mouse"
  },
  "identifiers": {
    "sku": null,
    "ean": null,
    "upc": null,
    "mpn": "910-006765"
  },
  "commerce": {
    "offers": [
      {
        "seller": { "name": "Store A", "url": "https://..." },
        "price": { "value": 459900, "currency": "COP" },
        "availability": "in_stock",
        "stock_quantity": null,
        "source": { "url": "...", "domain": "...", "scraped_at": "2026-08-15T20:00:00Z" }
      }
    ],
    "best_price": { "value": 459900, "currency": "COP" }   // derived convenience pointer
  },
  "description": {
    "short": null,
    "full": "...",
    "tags": ["gaming", "wireless"]
  },
  "specifications": {
    "weight_g": 106,
    "sensor_dpi": 25600,
    "sensor_type": "optical",
    "polling_rate_hz": 1000,
    "buttons": 13,
    "connectivity": ["usb", "wireless_2.4ghz"],
    "bluetooth": false,
    "wireless": true,
    "battery_life_hours": null,
    "dimensions_mm": { "length": null, "width": null, "height": null }
  },
  "specifications_extra": { "rgb_zones": 2 },   // unknown specs preserved, never discarded
  "use_cases": ["gaming", "competitive_gaming", "fps"],
  "features": ["wireless", "rgb", "programmable_buttons"],
  "media": { "images": ["https://..."] },
  "source": {
    "url": "...",
    "domain": "...",
    "scraped_at": "2026-08-15T20:00:00Z",
    "source_kind": "scraped|sample"
  },
  "schema_version": "1.0"
}
```

Reconciled contradiction: the brief's example showed a single `commerce` block, but §5
requires multi-seller representation. Resolved via `offers[]` + a `best_price` derived
pointer, which is the simplest structure satisfying both.

---

## 3. Taxonomy design

Explicit JSON files under `data/taxonomy/`:

| File                     | Purpose                                                    |
|--------------------------|------------------------------------------------------------|
| `categories.json`        | allowed categories (mouse, keyboard, headphones, monitor) |
| `subcategories.json`     | category → allowed subcategories                           |
| `use_cases.json`         | canonical use cases (gaming, office, fps, ...)             |
| `features.json`          | normalized feature names (wireless, rgb, ...)              |
| `connectivity_types.json`| canonical connectivity (usb, bluetooth, wireless_2.4ghz)   |
| `spec_names.json`        | category → canonical spec field + synonyms map             |
| `units.json`             | canonical units + aliases (ms, g, hz, in, ohm, ...)        |

Scrapers may not invent category names. The `TaxonomyLoader` caches lookups and exposes
`is_valid_*` / `resolve_synonym` helpers used by the normalizer and validator.

---

## 4. Normalization strategy

A `Normalizer` composes focused, single-purpose functions:

- **currency**: parse `"$499.900"`, `"$499,900"`, `"499900 COP"` → `{"value": 499900, "currency": "COP"}`.
  Treat `.`/`,` group separators by Colombian/locale heuristics; never guess currency not implied by source.
- **numbers**: regex extraction; reject malformed rather than fabricating.
- **units**: `units.json` alias map → canonical unit + numeric value (e.g. `"1 ms"`, `"1ms response"` → `response_time_ms: 1`).
- **brand**: synonym/canonical map (e.g. `"logi"` → `"Logitech"`); else Title-case.
- **availability**: map phrases → enum `{in_stock, out_of_stock, preorder, unknown}`.
- **features**: free-text → taxonomy feature set via keyword rules.
- **category**: infer from taxonomy + keywords; never invent.
- **specs**: per-category `SpecSchema` normalizes known fields; **unknown fields preserved verbatim** in `specifications_extra`.

Principles enforced in code:
- Missing → `null`. Never invent a value.
- Unmappable spec → preserved in `specifications_extra`, not dropped.

---

## 5. Deduplication strategy

Identity is **never** a seller URL. A deterministic fingerprint is built from the best
available manufacturer identifiers, in priority order:

1. `ean` or `upc` (GTIN) — global, strongest.
2. `mpn` + normalized `brand`.
3. normalized `brand` + normalized `model`.

`product_id = <category>_<fingerprint_hash>` (stable hash of the identity key).
Two records sharing a fingerprint merge into one canonical product; their offers are
concatenated in `commerce.offers` (each retaining its own `source`).
`best_price` is recomputed (min price) whenever offers change.

No identifier at all → flagged for review (rejected with `reason: insufficient_identity`),
since dedup would be unsafe.

---

## 6. Data validation strategy

`Validator` runs rule checks; first failure that is fatal routes the record to `data/rejected/`.
Non-fatal issues are collected as warnings but the record may still pass.

Minimum checks:
- required fields present (`identity.name`, `identity.category`, at least one offer price)
- valid category (taxonomy)
- valid price (number > 0) and valid currency
- valid URLs (offer source url, seller url, images)
- numeric specs are numbers and within plausible ranges (e.g. dpi > 0, refresh_rate_hz > 0)
- valid units for typed specs
- duplicate hint (identity fingerprint computable)
- source attribution present (`source.url`, `source.scraped_at`)

Rejected record shape:
```json
{
  "reason": "invalid_price",
  "fingerprint": "mouse_abc123",
  "source_record": { /* raw record */ },
  "validation_errors": ["Could not parse price: 'N/A'"],
  "rejected_at": "2026-08-15T20:00:00Z"
}
```

---

## 7. Scraper interface

```python
class BaseScraper(ABC):
    name: str
    source_kind: str  # "scraped" | "sample"

    @abstractmethod
    def iter_raw_records(self) -> Iterator[RawRecord]: ...

    def fetch(self, url: str) -> str: ...   # provided by HttpMixin (robots, retries, cache)
```

`HttpMixin` provides: `robots.txt` check, rate limiting, exponential-backoff retries,
on-disk cache keyed by URL, and a per-source `seen-urls` set persisted to
`pipeline_state.json` for resumable execution.

`RawRecord` (raw JSONL shape) is exactly the structure given in the brief:
`{ source: {url,domain,scraped_at}, raw: {title, price_text, description, specifications, images} }`.

---

## 8. Project directory structure

```text
commercial-ai-data/
├── src/commercial_ai/
│   ├── __init__.py
│   ├── models.py                 # RawRecord, CanonicalProduct, Offer, RejectedRecord
│   ├── taxonomy/                 # loader + registry
│   ├── scrapers/                 # base, http client, sample source
│   ├── normalization/            # currency/numbers/units/brand/availability/features/specs
│   ├── validation/
│   ├── deduplication/
│   ├── storage/                  # jsonl writer, pipeline state
│   ├── derived/                  # ML feature flattening (Parquet/CSV)
│   └── pipelines/                # orchestration
├── data/
│   ├── raw/                      # *.jsonl
│   ├── normalized/               # products.jsonl
│   ├── rejected/                 # *.jsonl
│   ├── taxonomy/                 # *.json
│   ├── interactions/             # reserved for future interactions
│   ├── derived/                  # *.parquet, *.csv (labeled "derived")
│   └── sample/                   # clearly-labeled sample fixtures
├── tests/
├── scripts/run_pipeline.py
├── config/config.yaml
├── logs/
├── README.md
├── DESIGN.md
└── pyproject.toml
```

---

## 9. Example raw record

```json
{
  "source": {
    "url": "https://example-store.co/producto/logitech-g502-x-plus",
    "domain": "example-store.co",
    "scraped_at": "2026-08-15T20:00:00Z",
    "source_kind": "sample"
  },
  "raw": {
    "title": "Mouse Logitech G502 X PLUS Inalámbrico RGB 25600 DPI",
    "price_text": "$459.900",
    "description": "Mouse gamer inalámbrico, sensor HERO 25600 DPI...",
    "specifications": {
      "Peso": "106 g",
      "DPI": "25600",
      "Sensor": "óptico HERO",
      "Tasa de sondeo": "1000 Hz",
      "Botones": "13",
      "Conectividad": "USB / Inalámbrico 2.4 GHz",
      "Bluetooth": "No",
      "RGB": "Sí",
      "Modelo": "910-006765"
    },
    "images": ["https://example-store.co/img/g502x-1.jpg"]
  }
}
```

---

## 10. Example normalized record

See the canonical schema in §2. The example raw record above normalizes to a product with
`product_id = "mouse_<hash>"`, offers from `example-store.co`, specs normalized
(`sensor_dpi: 25600`, `polling_rate_hz: 1000`, `weight_g: 106`, etc.), unknown spec `rgb_zones`
preserved in `specifications_extra`, and `use_cases: ["gaming","competitive_gaming","fps"]`.

---

## 11. Example rejected record

```json
{
  "reason": "invalid_price",
  "fingerprint": null,
  "source_record": {
    "source": { "url": "https://example-store.co/producto/x", "domain": "example-store.co",
                "scraped_at": "2026-08-15T20:00:00Z", "source_kind": "sample" },
    "raw": { "title": "Monitor X", "price_text": "Consultar", "specifications": {}, "images": [] }
  },
  "validation_errors": ["Could not parse price: 'Consultar'"],
  "rejected_at": "2026-08-15T20:00:00Z"
}
```

---

## 12. Plan for future ML integration

The product schema preserves attributes destined to become features: price, category,
use_cases, weight, connectivity, performance specs, feature availability, availability.

Future training-example shape (built later, not now):
```text
Customer requirements (LLM → structured) + Product characteristics + Interaction = Training example
```

`data/derived/` is reserved for flattened ML-ready vectors clearly tagged `derived=true`.
The current pipeline only **flattens existing attributes** (no predictions, no synthetic
labels). Later phases will add:
- candidate filtering by structured requirements
- a ranking/suitability model trained on interaction history (`data/interactions/`)
- LLM explanation layer over ranked candidates

No ML predictions are generated in this phase.

---

## Resolved contradictions (pre-implementation review)

1. **Single `commerce` block vs multi-seller offers** → `commerce.offers[]` + derived `best_price`.
2. **"Use null for missing" vs "preserve unknown specs"** → typed canonical fields use `null`;
   unmappable specs go to `specifications_extra` verbatim (preserved, not fabricated).
3. **`product_id` "internal unique" vs "no seller URL"** → deterministic hash of manufacturer
   identity fingerprint, never the URL.
4. **Honest data** → sample fixtures are explicitly `source_kind="sample"`; never presented as real.
