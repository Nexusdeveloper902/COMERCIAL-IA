"""Recommender data models: Requirement, Interaction, Compatibility, TrainingExample.

These schemas bridge the product dataset (built in phase 1) and the future
recommendation ML system. They define exactly what a training example looks like
so we know what behavioral data to collect/synthesize rather than scraping blindly.

Design principle (shared with the product pipeline): never invent values.
Missing product specs yield ``null`` compatibility, not ``False`` — "unknown" is
distinct from "does not meet".

These are *schema + derivation* only. No ML model is trained here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# 1. Requirement (output of the LLM interpreting a natural-language request)
# ---------------------------------------------------------------------------


@dataclass
class Budget:
    """Customer budget. Keeps original currency + COP (mirrors product prices)."""
    min: float | int | None = None
    max: float | int | None = None
    currency: str = "COP"
    max_cop: float | int | None = None  # derived FX conversion of max

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Requirement:
    """Structured interpretation of a customer's natural-language request.

    This is what the LLM produces from "quiero un mouse gamer inalámbrico para FPS
    por menos de 300 mil". It is the LEFT input to a training example.
    """
    request_id: str
    raw_text: str
    interpreted_at: str = field(default_factory=_now_iso)
    category: str | None = None
    subcategory: str | None = None
    budget: Budget | None = None
    use_cases: list[str] = field(default_factory=list)
    required_features: list[str] = field(default_factory=list)   # hard constraints
    preferred_features: list[str] = field(default_factory=list)  # soft / nice-to-have
    # Category-specific structured constraints mirroring product specs.
    # e.g. monitor: {"min_refresh_rate_hz": 144, "max_response_time_ms": 1}
    constraints: dict[str, Any] = field(default_factory=dict)
    # Per-dimension importance weights (0..1) from a fixed dimensions taxonomy.
    importance: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None  # LLM self-reported confidence (0..1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "raw_text": self.raw_text,
            "interpreted_at": self.interpreted_at,
            "category": self.category,
            "subcategory": self.subcategory,
            "budget": self.budget.to_dict() if self.budget else None,
            "use_cases": list(self.use_cases),
            "required_features": list(self.required_features),
            "preferred_features": list(self.preferred_features),
            "constraints": dict(self.constraints),
            "importance": dict(self.importance),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Requirement":
        b = d.get("budget")
        budget = Budget(**b) if b else None
        return cls(
            request_id=d["request_id"],
            raw_text=d.get("raw_text", ""),
            interpreted_at=d.get("interpreted_at") or _now_iso(),
            category=d.get("category"),
            subcategory=d.get("subcategory"),
            budget=budget,
            use_cases=list(d.get("use_cases") or []),
            required_features=list(d.get("required_features") or []),
            preferred_features=list(d.get("preferred_features") or []),
            constraints=dict(d.get("constraints") or {}),
            importance=dict(d.get("importance") or {}),
            confidence=d.get("confidence"),
        )


# ---------------------------------------------------------------------------
# 2. Interaction (behavioral signal tying a requirement to a product)
# ---------------------------------------------------------------------------

# Event types and their default suitability contribution.
EVENT_SUITABILITY: dict[str, float] = {
    "purchase": 1.0,
    "add_to_cart": 0.7,
    "click": 0.4,
    "view": 0.2,
    "reject": 0.0,
}

VALID_LABEL_SOURCES = {"real_interaction", "synthetic", "heuristic"}


@dataclass
class Interaction:
    """A customer/product interaction in the context of a specific request.

    The ``requirement_id`` is crucial: an interaction is only meaningful relative
    to the request that produced the candidate set. Clicking a mouse when
    searching for a keyboard is a different signal than clicking it when
    searching for a gaming mouse.
    """
    interaction_id: str
    customer_id: str  # anonymized
    product_id: str
    requirement_id: str
    event_type: str  # view|click|add_to_cart|purchase|reject|rating
    timestamp: str = field(default_factory=_now_iso)
    rating: float | None = None  # 0..1 explicit rating, if event_type == "rating"
    context: dict[str, Any] = field(default_factory=dict)  # position, session, etc.
    explicit_feedback: str | None = None  # free-text reason, e.g. "too heavy"
    label_source: str = "real_interaction"  # real_interaction|synthetic|heuristic

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Interaction":
        return cls(
            interaction_id=d["interaction_id"],
            customer_id=d["customer_id"],
            product_id=d["product_id"],
            requirement_id=d["requirement_id"],
            event_type=d["event_type"],
            timestamp=d.get("timestamp") or _now_iso(),
            rating=d.get("rating"),
            context=dict(d.get("context") or {}),
            explicit_feedback=d.get("explicit_feedback"),
            label_source=d.get("label_source", "real_interaction"),
        )

    def suitability_from_event(self) -> float | None:
        """Map the interaction to a 0..1 suitability signal.

        Explicit rating wins; otherwise the event-type map; ``reject`` -> 0.0.
        Returns None for unknown event types (not invented).
        """
        if self.event_type == "rating":
            return self.rating
        return EVENT_SUITABILITY.get(self.event_type)


# ---------------------------------------------------------------------------
# 3. Compatibility (derived: requirement ∩ product)
# ---------------------------------------------------------------------------


@dataclass
class Compatibility:
    """How well a product satisfies a requirement's hard constraints.

    All fields are derived from (requirement, product). ``None`` means "unknown"
    (a needed spec is missing on the product) — distinct from ``False`` (product
    violates the constraint). This distinction matters: filtering out a product
    for an unknown spec would lose valid candidates.
    """
    category_match: bool | None = None
    meets_budget: bool | None = None
    meets_required_features: list[str] = field(default_factory=list)   # satisfied
    missing_required_features: list[str] = field(default_factory=list)  # not on product
    violated_required_features: list[str] = field(default_factory=list)  # product has opposite
    meets_constraints: dict[str, bool | None] = field(default_factory=dict)
    use_case_overlap: list[str] = field(default_factory=list)
    preferred_feature_count: int = 0
    preferred_feature_total: int = 0

    @property
    def passes_hard_filter(self) -> bool:
        """True only if all hard constraints are satisfied (unknowns do NOT fail)."""
        if self.category_match is False:
            return False
        if self.meets_budget is False:
            return False
        if self.violated_required_features:
            return False
        if any(v is False for v in self.meets_constraints.values()):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_match": self.category_match,
            "meets_budget": self.meets_budget,
            "meets_required_features": list(self.meets_required_features),
            "missing_required_features": list(self.missing_required_features),
            "violated_required_features": list(self.violated_required_features),
            "meets_constraints": dict(self.meets_constraints),
            "use_case_overlap": list(self.use_case_overlap),
            "preferred_feature_count": self.preferred_feature_count,
            "preferred_feature_total": self.preferred_feature_total,
            "passes_hard_filter": self.passes_hard_filter,
        }


# ---------------------------------------------------------------------------
# 4. TrainingExample (one ML row)
# ---------------------------------------------------------------------------


@dataclass
class TrainingExample:
    """One ML training row: requirement + product + interaction -> labeled example.

    Tagged ``derived=true``. The target (``suitability``) is derived from the
    interaction outcome, NOT predicted by a model. The model (future) will learn
    to predict ``suitability`` from the requirement + product + compatibility
    features.
    """
    derived: bool
    example_id: str
    request_id: str
    product_id: str
    customer_id: str
    # inputs
    requirement: dict[str, Any]
    product: dict[str, Any]
    compatibility: dict[str, Any]
    interaction: dict[str, Any]
    # target
    suitability: float | None
    label_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "derived": self.derived,
            "example_id": self.example_id,
            "request_id": self.request_id,
            "product_id": self.product_id,
            "customer_id": self.customer_id,
            "requirement": self.requirement,
            "product": self.product,
            "compatibility": self.compatibility,
            "interaction": self.interaction,
            "suitability": self.suitability,
            "label_source": self.label_source,
        }
