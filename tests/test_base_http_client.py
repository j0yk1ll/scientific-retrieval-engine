from __future__ import annotations

from typing import Any, Iterable, Optional

import pytest

from retrieval.clients.base import (
    BaseHttpClient,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    RequestRejectedError,
    UnauthorizedError,
    UpstreamError,
)


class _StubSession:
    def __init__(self, responses: Iterable[Any]):
        self._responses = list(responses)
        self.headers: dict[str, str] = {}
        self.calls = 0

    def request(self, method: str, url: str, timeout: float = 0, **_: Any):
        self.calls += 1
        try:
            return self._responses[self.calls - 1]
        except IndexError:  # pragma: no cover - defensive guard for unexpected extra retries
            return self._responses[-1]


class _DummyClient(BaseHttpClient):
    BASE_URL = "https://example.test"

    def __init__(self, responses: Iterable[Any]):
        super().__init__(session=_StubSession(responses))

    @property
    def stub_session(self) -> _StubSession:
        return self.session  # type: ignore[return-value]


def _make_response(status: int, body: str = "", headers: Optional[dict[str, str]] = None):
    import requests

    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    response.url = "https://example.test/resource"
    response.headers.update(headers or {})
    response.encoding = "utf-8"
    return response


def test_http_400_raises_request_rejected_error():
    response = _make_response(400, body="Bad request details" + "!" * 500)
    client = _DummyClient([response])

    with pytest.raises(RequestRejectedError) as excinfo:
        client._handle_response(response)

    assert excinfo.value.status == 400
    assert excinfo.value.body_excerpt is not None
    assert len(excinfo.value.body_excerpt) <= 200
    assert "Bad request details" in excinfo.value.body_excerpt


def test_http_401_and_403_raise_specific_rejection_errors():
    unauthorized = _make_response(401, body="token expired")
    forbidden = _make_response(403, body="denied")
    client = _DummyClient([unauthorized, forbidden])

    with pytest.raises(UnauthorizedError):
        client._handle_response(unauthorized)

    with pytest.raises(ForbiddenError):
        client._handle_response(forbidden)


def test_http_404_raises_not_found():
    response = _make_response(404)
    client = _DummyClient([response])

    with pytest.raises(NotFoundError):
        client._handle_response(response)


def test_http_429_retries_then_rate_limited_error_contains_retry_after_if_present():
    rate_limited = _make_response(429, headers={"Retry-After": "0"})
    client = _DummyClient([rate_limited, rate_limited, rate_limited])

    with pytest.raises(RateLimitedError) as excinfo:
        client._request("GET", "/resource")

    assert excinfo.value.retry_after == 0
    assert client.stub_session.calls == 3


def test_http_500_retries():
    server_error = _make_response(500)
    client = _DummyClient([server_error, server_error, server_error])

    with pytest.raises(UpstreamError):
        client._request("GET", "/resource")

    assert client.stub_session.calls == 3
