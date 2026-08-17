"""Build a TrainingExample from a Requirement + Product + Interaction.

This is the single function that produces one ML training row. It composes:
  requirement (LLM output)
    + product (canonical catalog)
    + interaction (behavioral signal)
    -> compatibility (derived)
    -> training example (derived, labeled)

The suitability label comes from the interaction (NOT predicted). No model here.
"""
from __future__ import annotations

import hashlib

from ..models import CanonicalProduct
from .compatibility import compute_compatibility
from .models import Interaction, Requirement, TrainingExample


def build_training_example(
    req: Requirement,
    product: CanonicalProduct,
    interaction: Interaction,
) -> TrainingExample:
    """Assemble one labeled training example.

    The example_id is a deterministic hash of (request_id, product_id,
    interaction_id) so re-deriving the same inputs yields the same id.
    """
    comp = compute_compatibility(req, product)
    suitability = interaction.suitability_from_event()

    raw = f"{req.request_id}|{product.product_id}|{interaction.interaction_id}"
    example_id = "ex_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    return TrainingExample(
        derived=True,
        example_id=example_id,
        request_id=req.request_id,
        product_id=product.product_id,
        customer_id=interaction.customer_id,
        requirement=req.to_dict(),
        product=product.to_dict(),
        compatibility=comp.to_dict(),
        interaction=interaction.to_dict(),
        suitability=suitability,
        label_source=interaction.label_source,
    )
