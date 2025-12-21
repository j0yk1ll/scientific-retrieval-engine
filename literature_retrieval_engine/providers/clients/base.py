"""Shared HTTP client utilities with retry and error handling."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": "scientific-retrieval-engine",
    "Accept": "application/json",
}

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

RETRY_STOP_AFTER_ATTEMPT = 3

BASE_WAIT_MULTIPLIER = 0.5
BASE_WAIT_MIN_SECONDS = 0.5
BASE_WAIT_MAX_SECONDS = 8

RATE_LIMIT_WAIT_MULTIPLIER = 0.75
RATE_LIMIT_WAIT_MIN_SECONDS = 1.0
RATE_LIMIT_WAIT_MAX_SECONDS = 12

_shared_session: Optional[requests.Session] = None


class ClientError(Exception):
    """Base exception for HTTP client errors."""


class NotFoundError(ClientError):
    """Raised when a requested resource cannot be found (HTTP 404)."""


class RateLimitedError(ClientError):
    """Raised when the upstream service responds with a rate limit (HTTP 429)."""

    def __init__(self, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class RequestRejectedError(ClientError):
    """Raised when the upstream rejects the request (HTTP 4xx, excluding 404/429)."""

    def __init__(self, status: int, message: str, body_excerpt: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.body_excerpt = body_excerpt


class UnauthorizedError(RequestRejectedError):
    """Raised for HTTP 401 responses when authentication is required or has failed."""


class ForbiddenError(RequestRejectedError):
    """Raised for HTTP 403 responses when access is forbidden."""


class UpstreamError(ClientError):
    """Raised when the upstream service fails after retries."""


class RetryableResponseError(Exception):
    """Internal exception used to trigger retries for retryable responses."""

    def __init__(self, response: requests.Response):
        super().__init__("Retryable response received")
        self.response = response


def _get_shared_session() -> requests.Session:
    """Return a shared :class:`requests.Session` with default headers."""

    global _shared_session
    if _shared_session is None:
        _shared_session = requests.Session()
        _shared_session.headers.update(DEFAULT_HEADERS)
    else:
        for key, value in DEFAULT_HEADERS.items():
            _shared_session.headers.setdefault(key, value)
    return _shared_session


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None

    if value.isdigit():
        return float(value)

    try:
        retry_time = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if retry_time is None:
        return None

    if retry_time.tzinfo is None:
        retry_time = retry_time.replace(tzinfo=timezone.utc)

    delay = (retry_time - datetime.now(timezone.utc)).total_seconds()
    return max(delay, 0.0)


_base_wait = wait_exponential(
    multiplier=BASE_WAIT_MULTIPLIER, min=BASE_WAIT_MIN_SECONDS, max=BASE_WAIT_MAX_SECONDS
)
_rate_limit_wait = wait_exponential(
    multiplier=RATE_LIMIT_WAIT_MULTIPLIER,
    min=RATE_LIMIT_WAIT_MIN_SECONDS,
    max=RATE_LIMIT_WAIT_MAX_SECONDS,
)

_BODY_EXCERPT_LIMIT = 200


def _retry_wait(retry_state: RetryCallState) -> float:
    """Custom wait strategy honoring Retry-After headers when available."""

    wait_seconds: Optional[float] = None
    max_wait_seconds: Optional[float] = None
    wait_strategy = _base_wait
    if retry_state.outcome is not None and retry_state.outcome.failed:
        exception = retry_state.outcome.exception()
        if isinstance(exception, RetryableResponseError):
            if exception.response.status_code == 429:
                wait_strategy = _rate_limit_wait
                max_wait_seconds = RATE_LIMIT_WAIT_MAX_SECONDS
            wait_seconds = _parse_retry_after(exception.response.headers.get("Retry-After"))

    if wait_seconds is not None:
        return wait_seconds

    fallback = wait_strategy(retry_state)
    if max_wait_seconds is None:
        max_wait_seconds = BASE_WAIT_MAX_SECONDS

    jittered_min = fallback * 0.5
    jittered_max = min(fallback * 1.5, max_wait_seconds)
    return random.uniform(jittered_min, jittered_max)


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    args = retry_state.args or ()
    client = args[0] if args else None
    if not getattr(client, "debug_logging", False):
        return

    method = args[1] if len(args) > 1 else "UNKNOWN"
    url = args[2] if len(args) > 2 else ""
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    reason = f" due to {exception}" if exception else ""
    method_str = method.upper() if isinstance(method, str) else str(method)

    logger.debug(
        "Retry attempt %s for %s %s%s",
        retry_state.attempt_number,
        method_str,
        url,
        reason,
    )


def _sanitize_excerpt(text: str, max_length: int) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:max_length]


def _get_body_excerpt(response: requests.Response) -> Optional[str]:
    try:
        body_text = response.text
    except Exception:
        return None

    if not body_text:
        return None

    return _sanitize_excerpt(body_text, _BODY_EXCERPT_LIMIT)


class BaseHttpClient:
    """Base class providing shared HTTP behavior for retrieval clients.

    Retries are applied to network failures raised by ``requests`` and HTTP
    responses with status codes in :data:`RETRYABLE_STATUS_CODES`. After the
    retry budget is exhausted, HTTP 429 responses raise
    :class:`RateLimitedError` (including any parsed ``Retry-After`` hint) while
    5xx responses raise :class:`UpstreamError`. Both transport-level exceptions
    and retryable HTTP responses share the same retry budget; once exhausted,
    the final response is surfaced as a structured exception for clearer
    handling by callers.
    """

    BASE_URL = ""

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        debug_logging: bool = False,
    ) -> None:
        self.session = session or _get_shared_session()
        for key, value in DEFAULT_HEADERS.items():
            self.session.headers.setdefault(key, value)
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        self.debug_logging = debug_logging

    @retry(
        reraise=True,
        stop=stop_after_attempt(RETRY_STOP_AFTER_ATTEMPT),
        wait=_retry_wait,
        retry=retry_if_exception_type((requests.RequestException, RetryableResponseError)),
        before_sleep=_log_retry_attempt,
    )
    def _send(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        if response.status_code in RETRYABLE_STATUS_CODES:
            raise RetryableResponseError(response)
        return response

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        if self.debug_logging:
            logger.debug("HTTP %s %s", method.upper(), path)
        try:
            response = self._send(method, url, params=params, headers=headers, **kwargs)
        except RetryableResponseError as exc:
            response = exc.response
        except requests.RequestException as exc:  # pragma: no cover - network dependent
            raise UpstreamError(f"Request failed: {exc}") from exc

        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> requests.Response:
        status = response.status_code
        if status == 404:
            raise NotFoundError("Resource not found")
        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitedError("Rate limit exceeded", retry_after=retry_after)
        if 500 <= status < 600:
            excerpt = _get_body_excerpt(response)
            message = "Upstream service error"
            if excerpt:
                message = f"{message}: {excerpt}"
            raise UpstreamError(f"{message} ({status})")
        if 400 <= status < 500:
            excerpt = _get_body_excerpt(response)
            message = "Client request rejected"
            if excerpt:
                message = f"{message}: {excerpt}"
            if status == 401:
                raise UnauthorizedError(status, f"Unauthorized ({status})", body_excerpt=excerpt)
            if status == 403:
                raise ForbiddenError(status, f"Forbidden ({status})", body_excerpt=excerpt)
            raise RequestRejectedError(status, f"{message} ({status})", body_excerpt=excerpt)
        return response

