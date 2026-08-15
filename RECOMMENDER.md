# Recommender Training-Example Schema (Design)

> **Phase scope.** This document defines the schema that bridges the product
> dataset (phase 1) and the future recommendation ML system. It does **not**
> train or run a model. It answers the question: *what exactly does one training
> example for the recommender look like?* — so we know what behavioral data to
> collect/synthesize instead of scraping blindly.

## The future architecture this supports

```
Customer request (natural language)
      ↓
LLM interprets
      ↓
Requirement JSON
      ↓
Candidate filtering   ← hard constraints (passes_hard_filter)
      ↓
ML ranking            ← weighted compatibility features + importance
      ↓
Top products
      ↓
LLM explanation
      ↓
Customer
```

The schema below is designed so that:
- the **hard-constraint booleans** in `Compatibility` become the candidate filter;
- the **compatibility features + importance weights** become the ML ranker inputs;
- the **interaction outcome** becomes the training label (`suitability`).

## The three schemas

### 1. Requirement (LLM output)

The structured interpretation of a customer's natural-language request. This is
what the LLM produces. It is the **left input** to a training example.

```json
{
  "request_id": "req_001",
  "raw_text": "quiero un mouse gamer inalámbrico para FPS, liviano, máximo 300 mil",
  "interpreted_at": "2026-08-15T21:00:00Z",
  "category": "mouse",
  "subcategory": "gaming_mouse",
  "budget": {"min": null, "max": 300000, "currency": "COP", "max_cop": 300000},
  "use_cases": ["gaming", "competitive_gaming", "fps"],
  "required_features": ["wireless", "gaming_sensor"],
  "preferred_features": ["rgb", "lightweight"],
  "constraints": {
    "min_sensor_dpi": 12000,
    "max_weight_g": 110,
    "min_polling_rate_hz": 1000
  },
  "importance": {"performance": 1.0, "price": 0.8, "ergonomics": 0.7},
  "confidence": 0.9
}
```

Key fields:
- **`budget`** keeps original currency **and** `max_cop` (mirrors product prices),
  so a USD-budgeted request can still be compared against COP products.
- **`required_features`** are hard constraints (MUST have).
- **`preferred_features`** are soft (nice-to-have) — counted, not filtered.
- **`constraints`** are category-specific structured specs mirroring product specs,
  prefixed with `min_` / `max_` to indicate direction.
- **`importance`** is per-dimension weights (0..1) from a fixed dimensions taxonomy
  (`data/taxonomy/requirement_dimensions.json`). This is what lets the model weight
  compatibility features *per customer* — "I care a lot about performance, less
  about aesthetics".
- **`confidence`** is the LLM's self-reported confidence in its interpretation.

### 2. Interaction (behavioral signal)

A customer/product interaction **in the context of a specific request**. This is
the signal that becomes the training label.

```json
{
  "interaction_id": "int_001",
  "customer_id": "cust_anon_42",
  "product_id": "mouse_d4658c5bdf388725",
  "requirement_id": "req_001",
  "event_type": "purchase",
  "timestamp": "2026-08-15T21:05:00Z",
  "rating": null,
  "context": {"position": 1, "session": "sess_abc", "candidate_set_size": 5},
  "explicit_feedback": null,
  "label_source": "real_interaction"
}
```

Key points:
- **`requirement_id` is crucial.** An interaction is only meaningful relative to
  the request that produced the candidate set. Clicking a mouse when searching
  for a keyboard is a different signal than clicking it when searching for a
  gaming mouse.
- **`event_type` → suitability** map: `purchase`=1.0, `add_to_cart`=0.7,
  `click`=0.4, `view`=0.2, `reject`=0.0; `rating` uses the explicit 0..1 value.
- **`label_source`** is `real_interaction | synthetic | heuristic` — and this is
  the key to honest data: synthetic examples are **never** passed off as real
  (matches the project's core principle). This field tells us exactly what we
  need to collect (real) vs. what we can generate (synthetic/heuristic) while
  bootstrapping.

### 3. TrainingExample (one ML row)

Assembled by `build_training_example(requirement, product, interaction)`:

```text
Requirement  +  Product  +  Interaction
      ↓             ↓           ↓
      └─────────────┴───────────┘
                    ↓
            Compatibility (derived)
                    ↓
            TrainingExample (derived, labeled)
```

```json
{
  "derived": true,
  "example_id": "ex_88f319cf0115d18e",
  "request_id": "req_001",
  "product_id": "mouse_d4658c5bdf388725",
  "customer_id": "cust_anon_42",
  "requirement": { ... full Requirement JSON ... },
  "product":     { ... full canonical Product JSON ... },
  "compatibility": {
    "category_match": true,
    "meets_budget": false,
    "meets_required_features": ["wireless", "gaming_sensor"],
    "missing_required_features": [],
    "violated_required_features": [],
    "meets_constraints": {"min_sensor_dpi": true, "max_weight_g": true, "min_polling_rate_hz": true},
    "use_case_overlap": ["competitive_gaming", "fps", "gaming"],
    "preferred_feature_count": 2,
    "preferred_feature_total": 2,
    "passes_hard_filter": false
  },
  "interaction": { ... full Interaction JSON ... },
  "suitability": 1.0,
  "label_source": "real_interaction"
}
```

- **`derived: true`** marks this as derived data (not scraped).
- **`example_id`** is a deterministic hash of `(request_id, product_id, interaction_id)`
  so re-deriving the same inputs yields the same id (idempotent regeneration).
- **`suitability`** is the label, derived from the interaction — **not** a model
  prediction. The future model will learn to predict this from the inputs.

## The Compatibility layer (why it's the key)

`Compatibility` is a **derived** object: `requirement ∩ product`. It is the bridge
that makes `(requirement, product)` learnable. Its booleans are the candidate
filter; its richer fields (overlap counts, per-constraint results) plus the
requirement's `importance` weights are the ranker features.

### The "unknown ≠ false" rule (critical)

When a needed spec is missing on the product, compatibility is `null`, **not**
`False`. This distinction matters: filtering out a product for an unknown spec
would discard valid candidates. Only an explicit *violation* (product has the
spec and it fails the constraint) produces `False` and fails the hard filter.

| situation                         | result     | fails hard filter? |
|-----------------------------------|------------|--------------------|
| product meets constraint          | `true`     | no                 |
| product has spec, violates        | `false`    | yes                |
| product lacks spec entirely       | `null`     | no (unknown)       |

This applies to budget and category too: a product with no price → `meets_budget: null`.

## What this tells us to collect (the point of locking this down now)

Now that the training example is defined, we know exactly what behavioral data we
need — rather than scraping blindly:

| we need                | source                          | status            |
|------------------------|---------------------------------|-------------------|
| Product catalog        | scrapers (phase 1)              | ✅ built          |
| Requirement JSONs      | LLM interpreting requests       | 🔜 next phase     |
| Interactions (real)    | clickstream / purchase logs     | 🔜 instrument     |
| Interactions (bootstrap)| synthetic/heuristic, labeled  | ⚠️ allowed, tagged|

Because `label_source` is mandatory and typed, we can bootstrap a training set
with heuristic labels (e.g. "products meeting all hard constraints + high use-case
overlap → suitability 1.0") **without ever pretending they're real interactions**.
The model can later be retrained on real data as it arrives.

## Module layout

```
src/commercial_ai/recommender/
├── __init__.py          # public exports
├── models.py            # Requirement, Budget, Interaction, Compatibility, TrainingExample
├── compatibility.py     # compute_compatibility(req, product) -> Compatibility
└── builder.py           # build_training_example(req, product, interaction) -> TrainingExample
```

- `compute_compatibility` is pure: `(requirement, product) → Compatibility`. No ML.
- `build_training_example` composes the three inputs + compatibility into one row.

## Tests

- `tests/unit/test_compatibility.py` — 15 tests: category match/mismatch, budget
  met/violated/unknown, required features met/missing/violated, min/max constraints,
  unknown-spec-→-null, use-case overlap, preferred counts.
- `tests/unit/test_recommender_builder.py` — 8 tests: event→suitability map, rating
  override, deterministic example_id, full structure, synthetic labeling, reject→0.

## What is explicitly NOT here yet

- No LLM to interpret requests into `Requirement` (that's the next phase).
- No candidate-filter or ranking service over the live catalog.
- No ML model training/inference — only the schema and derivation that a future
  model will consume.
- No synthetic data generator yet — but the schema is ready for one, and its
  outputs would be tagged `label_source: synthetic`.
