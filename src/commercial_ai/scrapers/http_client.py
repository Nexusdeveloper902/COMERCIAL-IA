"""HTTP client with robots.txt respect, rate limiting, retries + cache.

Safety:
* respects robots.txt (configurable)
* rate-limits per domain
* exponential backoff retries on transient errors
* on-disk cache keyed by URL (avoid re-fetching known pages)
* identifies a friendly User-Agent
* Does NOT bypass auth / CAPTCHA / anti-bot protections.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)


class HttpClient:
    def __init__(
        self,
        cache_dir: str | Path = "data/.http_cache",
        user_agent: str = "commercial-ai-bot/0.1",
        rate_limit_seconds: float = 1.0,
        max_retries: int = 4,
        backoff_base: float = 1.5,
        respect_robots: bool = True,
        timeout: float = 20.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.rate_limit = rate_limit_seconds
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.respect_robots = respect_robots
        self.timeout = timeout
        self._last_request: dict[str, float] = {}  # domain -> ts
        self._robots: dict[str, RobotFileParser | None] = {}

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.txt"

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _can_fetch(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        domain = self._domain(url)
        if domain not in self._robots:
            rp = RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            try:
                txt = requests.get(
                    robots_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                ).text
                rp.parse(txt.splitlines())
                self._robots[domain] = rp
            except Exception as e:  # noqa: BLE001
                log.warning("robots.txt fetch failed for %s: %s (allowing by default)", domain, e)
                self._robots[domain] = None
        rp = self._robots[domain]
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def _rate_limit_wait(self, domain: str) -> None:
        last = self._last_request.get(domain, 0.0)
        elapsed = time.time() - last
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request[domain] = time.time()

    def get(self, url: str, use_cache: bool = True) -> str:
        """Fetch URL text with cache + retries. Raises on persistent failure."""
        if use_cache:
            cp = self._cache_path(url)
            if cp.exists():
                log.debug("cache hit: %s", url)
                return cp.read_text(encoding="utf-8")

        if not self._can_fetch(url):
            log.info("robots.txt disallows: %s (skipping)", url)
            raise PermissionError(f"robots.txt disallows fetching {url}")

        domain = self._domain(url)
        headers = {"User-Agent": self.user_agent}
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._rate_limit_wait(domain)
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                text = resp.text
                if use_cache:
                    self._cache_path(url).write_text(text, encoding="utf-8")
                return text
            except Exception as e:  # noqa: BLE001
                last_err = e
                wait = self.backoff_base ** attempt
                log.warning("fetch attempt %d/%d failed for %s: %s (retry in %.1fs)",
                            attempt, self.max_retries, url, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"failed to fetch {url} after {self.max_retries} attempts: {last_err}")

    def get_json(self, url: str, use_cache: bool = True) -> dict[str, Any] | None:
        """Fetch URL and parse as JSON. Returns None on fetch failure."""
        try:
            text = self.get(url, use_cache=use_cache)
        except Exception as e:  # noqa: BLE001
            log.error("get_json fetch failed for %s: %s", url, e)
            return None
        try:
            return json.loads(text)
        except Exception as e:  # noqa: BLE001
            log.error("get_json parse failed for %s: %s", url, e)
            return None
