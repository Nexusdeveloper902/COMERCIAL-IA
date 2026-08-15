"""Recommender schema layer: defines what a training example looks like.

This package does NOT train or run a model. It defines the three schemas that
bridge the product dataset and the future recommendation ML system:

* ``Requirement``   - structured interpretation of a customer request (LLM output).
* ``Interaction``   - behavioral signal tying a request to a product.
* ``TrainingExample`` - one labeled ML row (requirement + product + interaction).

plus ``Compatibility`` (derived: requirement ∩ product) and the builders that
assemble a training example.
"""
from .builder import build_training_example
from .compatibility import compute_compatibility
from .models import (
    Budget,
    Compatibility,
    Interaction,
    Requirement,
    TrainingExample,
)

__all__ = [
    "Budget",
    "Compatibility",
    "Interaction",
    "Requirement",
    "TrainingExample",
    "build_training_example",
    "compute_compatibility",
]
