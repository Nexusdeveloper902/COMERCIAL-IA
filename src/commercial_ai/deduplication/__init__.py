"""Deduplication: merge records sharing an identity fingerprint into one
canonical product with multiple seller offers."""
from .deduper import Deduplicator

__all__ = ["Deduplicator"]
