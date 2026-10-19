"""Shared HTTP helper: one session, a user agent, timeouts and simple retries."""
from __future__ import annotations

import time

import requests

USER_AGENT = "ceemea-brief/1.0 (research tool; github.com)"
_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def get(url: str, *, params: dict | None = None, timeout: int = 30, retries: int = 2) -> requests.Response:
    """GET with retries on connection errors and 5xx responses. Raises on final failure."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = _session.get(url, params=params, timeout=timeout)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} from {url}")
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:   # noqa: PERF203
            last_exc = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries + 1} attempts: {url}: {last_exc}")
