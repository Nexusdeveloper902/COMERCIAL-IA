"""Scrapers: source adapters producing raw records."""
from .base import BaseScraper
from .http_client import HttpClient
from .sample_source import SampleSourceScraper

__all__ = ["BaseScraper", "HttpClient", "SampleSourceScraper"]
