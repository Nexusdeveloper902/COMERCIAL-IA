"""Scrapers: source adapters producing raw records."""
from .base import BaseScraper
from .bestbuy import BestBuyScraper
from .http_client import HttpClient
from .mercadolibre import MercadoLibreScraper
from .sample_source import SampleSourceScraper
from .synthetic import SyntheticSourceScraper

__all__ = [
    "BaseScraper",
    "BestBuyScraper",
    "HttpClient",
    "MercadoLibreScraper",
    "SampleSourceScraper",
    "SyntheticSourceScraper",
]
