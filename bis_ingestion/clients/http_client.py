"""
http_client.py — Shared HTTP client with retry, rate limiting, and respectful crawling.

This module provides a single, reusable HTTP session used by all clients.
All requests go through this layer so that rate limiting and retry logic
is consistently applied across the entire pipeline.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional
from urllib.robotparser import RobotFileParser

import httpx

from bis_ingestion.config import (
    HEADERS,
    MAX_RETRIES,
    MAX_RETRY_BACKOFF,
    REQUEST_DELAY_MAX,
    REQUEST_DELAY_MIN,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_BASE,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# Cache robots.txt parsers per domain
_robot_cache: dict[str, RobotFileParser] = {}


def _get_robots(base_url: str) -> RobotFileParser:
    """Fetch and cache robots.txt for a given base URL."""
    if base_url not in _robot_cache:
        rp = RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        try:
            rp.read()
        except Exception as e:
            logger.warning("Could not fetch robots.txt for %s: %s", base_url, e)
        _robot_cache[base_url] = rp
    return _robot_cache[base_url]


def is_crawl_allowed(url: str, base_url: str) -> bool:
    """Return True if our User-Agent is allowed to fetch this URL."""
    rp = _get_robots(base_url)
    allowed = rp.can_fetch(USER_AGENT, url)
    if not allowed:
        logger.warning("robots.txt disallows: %s", url)
    return allowed


def _polite_delay() -> None:
    """Sleep for a random interval between REQUEST_DELAY_MIN and REQUEST_DELAY_MAX."""
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    logger.debug("Rate-limiting delay: %.2fs", delay)
    time.sleep(delay)


class BISHTTPClient:
    """
    Wrapper around httpx.Client with:
    - Conservative rate limiting
    - Automatic retry with exponential backoff
    - robots.txt compliance check
    - Request logging
    """

    def __init__(self, base_url: str = "", session_headers: Optional[dict] = None):
        self.base_url = base_url
        self._headers = {**HEADERS, **(session_headers or {})}
        self._client = httpx.Client(
            headers=self._headers,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            # Do NOT trust arbitrary redirects to non-gov domains
            max_redirects=5,
        )
        logger.info("BISHTTPClient initialised for base_url=%s", base_url or "generic")

    def get(
        self,
        url: str,
        params: Optional[dict] = None,
        skip_robots_check: bool = False,
    ) -> httpx.Response:
        """
        Perform a GET request with retry + polite delay.
        Raises httpx.HTTPStatusError on non-retryable HTTP errors.
        """
        # Robots check
        if not skip_robots_check and self.base_url:
            if not is_crawl_allowed(url, self.base_url):
                raise PermissionError(f"robots.txt disallows crawling: {url}")

        last_exc: Any = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                _polite_delay()
                logger.info("GET %s (attempt %d/%d)", url, attempt + 1, MAX_RETRIES + 1)
                response = self._client.get(url, params=params)
                response.raise_for_status()
                logger.debug("Response %d, %d bytes", response.status_code, len(response.content))
                return response
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 503, 502, 504):
                    # Retriable server-side issues
                    backoff = min(RETRY_BACKOFF_BASE ** attempt, MAX_RETRY_BACKOFF)
                    logger.warning(
                        "HTTP %d on %s — backing off %.1fs (attempt %d/%d)",
                        status, url, backoff, attempt + 1, MAX_RETRIES,
                    )
                    time.sleep(backoff)
                    last_exc = e
                    continue
                elif status == 404:
                    logger.warning("HTTP 404: %s — skipping", url)
                    raise
                else:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                backoff = min(RETRY_BACKOFF_BASE ** attempt, MAX_RETRY_BACKOFF)
                logger.warning(
                    "Network error on %s: %s — backing off %.1fs", url, e, backoff
                )
                time.sleep(backoff)
                last_exc = e

        raise RuntimeError(
            f"All {MAX_RETRIES + 1} attempts failed for {url}: {last_exc}"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BISHTTPClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
