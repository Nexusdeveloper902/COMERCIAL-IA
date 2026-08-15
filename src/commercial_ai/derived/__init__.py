"""Derived ML-ready feature flattening (labeled 'derived', no predictions)."""
from .ml_features import flatten_for_ml, write_ml_datasets

__all__ = ["flatten_for_ml", "write_ml_datasets"]
