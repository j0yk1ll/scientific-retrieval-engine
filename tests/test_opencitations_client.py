import requests

from retrieval.providers.clients.opencitations import OpenCitationsClient
from retrieval.core.models import Citation


class DummyResponse:
    def __init__(self, status_code: int, json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data or []
        self.headers = headers or {}

    def json(self):
        return self._json


def test_opencitations_retries_on_rate_limit(monkeypatch):
    calls = []
    responses = [
        DummyResponse(429, headers={"Retry-After": "0"}),
        DummyResponse(
            200,
            json_data=[
                {"citing": "10.1111/a", "cited": "10.2222/b", "creation": "2024-01-01"}
            ],
        ),
    ]

    session = requests.Session()

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append((method, url, timeout))
        return responses.pop(0)

    monkeypatch.setattr(session, "request", fake_request)

    client = OpenCitationsClient(session=session)
    citations = client.citations("10.9999/example")

    assert len(calls) == 2
    assert citations == [Citation(citing="10.1111/a", cited="10.2222/b", creation="2024-01-01")]


def test_opencitations_returns_empty_on_not_found(monkeypatch):
    session = requests.Session()
    responses = [DummyResponse(404)]

    def fake_request(method, url, timeout=None, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(session, "request", fake_request)

    client = OpenCitationsClient(session=session)

    assert client.citations("missing") == []


def test_opencitations_normalizes_doi_inputs(monkeypatch):
    session = requests.Session()
    calls = []
    responses = [
        DummyResponse(200, json_data=[{"citing": "a", "cited": "b", "creation": None}]),
        DummyResponse(200, json_data=[{"citing": "a", "cited": "b", "creation": None}]),
    ]

    def fake_request(method, url, timeout=None, **kwargs):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(session, "request", fake_request)

    client = OpenCitationsClient(session=session)

    client.citations("https://doi.org/10.1000/xyz")
    client.citations("10.1000/xyz")

    assert len(calls) == 2
    assert calls[0] == calls[1]
