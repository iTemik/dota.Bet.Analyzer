"""OpenDota HTTP access shared by every OpenDota request in the app.

OpenDota limits requests in two ways: HTTP 429 when the per-minute limit is used up (the free tier allows
about 60 requests per minute), and requests that time out or get the connection dropped when requests come
too often in a short time window. In both cases the request is postponed and repeated a few times instead of
failing right away.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Optional

import requests

from backend.logging_config import setup_logging

logger = setup_logging(__name__)

OPENDOTA_API = "https://api.opendota.com/api"
RATE_LIMIT_STATUS = 429
RATE_LIMIT_RETRIES = 3  # Repeats after the first rate-limited answer or timeout
RATE_LIMIT_WAITS = (10, 20, 40)  # Seconds to wait before each repeat when the API gives no Retry-After
RATE_LIMIT_MAX_WAIT = 60  # Never wait longer than this for one repeat
RETRY_ERRORS = (requests.Timeout, requests.ConnectionError)  # Short-window protection: no answer instead of 429

WaitCallback = Callable[[int], None]


class OpenDotaError(Exception):
    """An OpenDota request failed after all repeats.

    Attributes:
        status: HTTP status code (503 for network errors, 502 for invalid JSON)
        code: NETWORK_ERROR, HTTP_ERROR or JSON_DECODE_ERROR
        message: Human-readable error message
    """

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def opendota_url(path: str) -> str:
    """Full OpenDota URL for an API path such as "/teams/123" (full URLs are returned as is)."""
    return path if path.startswith("http") else f"{OPENDOTA_API}{path}"


def _retry_delay(resp: Optional[requests.Response], attempt: int) -> int:
    """Seconds to wait before repeating a request (Retry-After header when present)."""
    retry_after = resp.headers.get("Retry-After") if resp is not None and resp.headers else None
    try:
        if retry_after is not None:
            return max(1, min(int(retry_after), RATE_LIMIT_MAX_WAIT))
    except (TypeError, ValueError):
        pass
    return RATE_LIMIT_WAITS[min(attempt, len(RATE_LIMIT_WAITS) - 1)]


def opendota_get(
    url: str,
    params: Optional[dict[str, Any]] = None,
    timeout: float = 30,
    on_wait: Optional[WaitCallback] = None,
) -> requests.Response:
    """GET an OpenDota URL, postponing and repeating the request on HTTP 429, timeouts and dropped connections.

    Args:
        url: URL or API path (e.g. "/teams/123")
        params: Optional query parameters
        timeout: Request timeout in seconds
        on_wait: Called with the delay in seconds before each repeat (e.g. to report progress)

    Returns:
        The last response (still HTTP 429 when every repeat was rate-limited)

    Raises:
        requests.RequestException: On network errors, or a timeout after the last repeat
    """
    url = opendota_url(url)
    kwargs: dict[str, Any] = {"timeout": timeout}
    if params is not None:
        kwargs["params"] = params
    attempt = 0
    while True:
        resp: Optional[requests.Response] = None
        try:
            resp = requests.get(url, **kwargs)
        except RETRY_ERRORS as exc:
            if attempt >= RATE_LIMIT_RETRIES:
                raise
            reason = f"no answer ({type(exc).__name__})"
        else:
            if resp.status_code != RATE_LIMIT_STATUS or attempt >= RATE_LIMIT_RETRIES:
                return resp
            reason = "rate limit reached"
        delay = _retry_delay(resp, attempt)
        attempt += 1
        logger.warning(f"OpenDota {reason} for {url}, retry {attempt}/{RATE_LIMIT_RETRIES} in {delay}s")
        if on_wait is not None:
            on_wait(delay)
        time.sleep(delay)


def get_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    timeout: float = 30,
    on_wait: Optional[WaitCallback] = None,
) -> Any:
    """GET an OpenDota URL with the shared repeat rules and return the parsed JSON.

    Args:
        url: URL or API path (e.g. "/teams/123")
        params: Optional query parameters
        timeout: Request timeout in seconds
        on_wait: Called with the delay in seconds before each repeat

    Returns:
        Parsed JSON payload

    Raises:
        OpenDotaError: On network errors, non-200 answers or invalid JSON
    """
    try:
        resp = opendota_get(url, params=params, timeout=timeout, on_wait=on_wait)
    except Exception as exc:
        raise OpenDotaError(503, "NETWORK_ERROR", f"Network error fetching data: {exc}") from exc

    if resp.status_code != 200:
        raise OpenDotaError(resp.status_code, "HTTP_ERROR", f"HTTP {resp.status_code} from API")

    try:
        return resp.json()
    except Exception as exc:
        raise OpenDotaError(502, "JSON_DECODE_ERROR", f"Invalid JSON response: {exc}") from exc
