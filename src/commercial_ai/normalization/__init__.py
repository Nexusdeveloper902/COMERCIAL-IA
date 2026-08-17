"""Normalization pipeline: raw record -> canonical product (before validation)."""
from .fx import CurrencyConverter, enrich_prices_cop
from .normalizer import Normalizer

__all__ = ["CurrencyConverter", "Normalizer", "enrich_prices_cop"]
