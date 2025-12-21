from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote

import requests

from literature_retrieval_engine.providers.clients.openalex import OpenAlexClient


class _CapturingSession:
    def __init__(self, responses: Iterable[requests.Response]):
        self._responses = list(responses)
        self.headers: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, timeout: float = 0, params: Any = None, **_: Any):
        self.calls.append({"method": method, "url": url, "params": params})
        return self._responses[len(self.calls) - 1]


def _make_response(status: int, payload: Optional[dict[str, Any]] = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    if payload is not None:
        response._content = json.dumps(payload).encode()
        response.headers["Content-Type"] = "application/json"
    response.url = "https://api.openalex.org/works"
    response.encoding = "utf-8"
    return response


def _load_fixture(name: str) -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text())


def test_get_by_doi_resolves_via_external_id():
    payload = _load_fixture("openalex_work_sample.json")
    session = _CapturingSession([_make_response(200, payload)])
    client = OpenAlexClient(session=session)

    work = client.get_work_by_doi("10.1234/example")

    assert work is not None
    doi_url = "https://doi.org/10.1234/example"
    expected_path = quote(doi_url, safe="")
    assert session.calls[0]["url"].endswith(f"/works/{expected_path}")


def test_get_by_doi_falls_back_to_filter_when_external_id_fails():
    payload = _load_fixture("openalex_work_sample.json")
    session = _CapturingSession(
        [
            _make_response(404),
            _make_response(200, {"results": [payload]}),
        ]
    )
    client = OpenAlexClient(session=session)

    work = client.get_work_by_doi("10.1234/example")

    assert work is not None
    doi_url = "https://doi.org/10.1234/example"
    assert session.calls[1]["params"] == {"filter": f"doi:{doi_url}"}


def test_get_work_by_doi_filter_uses_filter_param_and_returns_work():
    payload = _load_fixture("openalex_work_sample.json")
    session = _CapturingSession([_make_response(200, {"results": [payload]})])
    client = OpenAlexClient(session=session)

    work = client.get_work_by_doi_filter("https://doi.org/10.1234/example")

    assert work is not None
    assert session.calls[0]["url"].endswith("/works")
    assert session.calls[0]["params"] == {"filter": "doi:https://doi.org/10.1234/example"}


def test_get_work_by_external_id_encodes_path_and_logs_non_200(caplog):
    doi_url = "https://doi.org/10.5555/abc:def/ghi"
    session = _CapturingSession([_make_response(403)])
    client = OpenAlexClient(session=session)

    caplog.set_level(logging.DEBUG, logger="literature_retrieval_engine.providers.clients.openalex")
    work = client.get_work_by_external_id(doi_url)

    assert work is None
    expected_path = quote(doi_url, safe="")
    assert session.calls[0]["url"].endswith(f"/works/{expected_path}")
    assert any("status=403" in record.message for record in caplog.records)
