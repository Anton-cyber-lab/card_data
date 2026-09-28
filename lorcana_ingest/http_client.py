"""HTTP fetching with pacing, retry/backoff and a hard request cap."""

from __future__ import annotations

import logging
import time

import requests

from lorcana_ingest.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://tcgcsv.com"
THROTTLE_WAIT_SECONDS = 610  # tcgcsv throttles an IP for ~10 minutes on 429


class TooManyRequestsError(Exception):
    """Raised when the run's safety cap or a repeated 429 stops the run."""


class Fetcher:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": config.user_agent})
        self.request_count = 0
        self._throttled_once = False

    def get_json(self, path: str) -> dict:
        url = f"{BASE_URL}{path}"
        response = self._get_with_retry(url)
        response.raise_for_status()
        return response.json()

    def _get_with_retry(self, url: str) -> requests.Response:
        attempt = 0
        while True:
            if self.request_count >= self._config.max_requests_per_run:
                raise TooManyRequestsError(
                    f"Safety cap of {self._config.max_requests_per_run} requests reached"
                )

            self.request_count += 1
            try:
                response = self._session.get(url, timeout=self._config.request_timeout_seconds)
            except requests.RequestException as exc:
                if attempt >= self._config.retry_count:
                    raise
                attempt += 1
                wait = 2 ** attempt
                logger.warning("Request error on %s: %s, retry in %ss", url, exc, wait)
                time.sleep(wait)
                continue
            finally:
                time.sleep(self._config.request_pause_seconds)

            if response.status_code == 429:
                if self._throttled_once:
                    raise TooManyRequestsError("Throttled twice, aborting run")
                self._throttled_once = True
                logger.warning("429 on %s, waiting %ss", url, THROTTLE_WAIT_SECONDS)
                time.sleep(THROTTLE_WAIT_SECONDS)
                continue

            if response.status_code >= 500 and attempt < self._config.retry_count:
                attempt += 1
                wait = 2 ** attempt
                logger.warning("%s on %s, retry in %ss", response.status_code, url, wait)
                time.sleep(wait)
                continue

            return response
