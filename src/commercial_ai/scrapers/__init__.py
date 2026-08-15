"""Scrapers: source adapters producing raw records."""
from .base import BaseScraper
from .bestbuy import BestBuyScraper
from .http_client import HttpClient
from .sample_source import SampleSourceScraper

__all__ = ["BaseScraper", "BestBuyScraper", "HttpClient", "SampleSourceScraper"]
