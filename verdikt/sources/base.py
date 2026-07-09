"""A thin, uniform HTTP client shared by all five data sources.

Every source (Open Targets, ClinicalTrials.gov, ChEMBL, PubMed, openFDA) speaks
a different dialect, but they all go through the same transport here so we get
one consistent story for: sessions, retries, polite rate limiting, timeouts,
in-process caching, and error handling.

A `BaseSource` also carries display metadata (`key`, `label`, `homepage`) and a
`.health()` probe, so the front end can render a uniform "source chip" and the
investigation view can light each source up as it is queried.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import CONFIG, Config


class SourceError(RuntimeError):
    """Raised when a source cannot be reached or returns an unusable payload."""


# One shared, connection-pooled session with sane retry behaviour for all sources.
def _build_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": cfg.user_agent, "Accept": "application/json"})
    return session


_SESSION: requests.Session | None = None


def get_session(cfg: Config = CONFIG) -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = _build_session(cfg)
    return _SESSION


class BaseSource:
    """Base class every source client inherits.

    Subclasses set the class attributes below and call `self._get(...)` /
    `self._post(...)`; the transport, caching and rate limiting are handled here.
    """

    key: str = "source"          # short machine id, e.g. "opentargets"
    label: str = "Source"        # human label, e.g. "Open Targets"
    homepage: str = ""           # where a user can learn more
    base_url: str = ""           # API root
    min_interval: float = 0.0    # seconds to wait between calls (politeness)

    def __init__(self, config: Config = CONFIG):
        self.config = config
        self.session = get_session(config)
        self._cache: dict[Any, Any] = {}
        self._lock = threading.Lock()
        self._last_call = 0.0

    # -- politeness ---------------------------------------------------------
    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    # -- core transport -----------------------------------------------------
    def _request(self, method: str, url: str, *, cache_key: Any = None, **kwargs) -> Any:
        if cache_key is not None:
            # In-memory first (this run), then disk (previous runs — nearly free).
            if cache_key in self._cache:
                return self._cache[cache_key]
            from ..cache import SOURCE_TTL, get as cache_get

            disk = cache_get(self.key, cache_key, ttl=SOURCE_TTL)
            if disk is not None:
                self._cache[cache_key] = disk
                return disk

        self._throttle()
        kwargs.setdefault("timeout", self.config.timeout)
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise SourceError(f"{self.label}: request failed ({exc})") from exc

        if resp.status_code >= 400:
            raise SourceError(
                f"{self.label}: HTTP {resp.status_code} for {url} — {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError(f"{self.label}: non-JSON response from {url}") from exc

        if cache_key is not None:
            self._cache[cache_key] = data
            from ..cache import put as cache_put

            cache_put(self.key, cache_key, data)
        return data

    def _get(self, path: str = "", *, params: dict | None = None, cache_key: Any = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return self._request("GET", url, params=params, cache_key=cache_key)

    def _post(self, path: str = "", *, json: dict | None = None, cache_key: Any = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return self._request("POST", url, json=json, cache_key=cache_key)

    # -- metadata for the UI ------------------------------------------------
    def describe(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label, "homepage": self.homepage}

    def health(self) -> bool:
        """Cheap reachability probe; subclasses may override with a real ping."""
        try:
            self.session.head(self.base_url, timeout=self.config.timeout)
            return True
        except requests.RequestException:
            return False
