import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from retrieval.discovery.openalex import OpenAlexClient


@pytest.fixture()
def openalex_work_payload() -> dict:
    fixture_path = Path("tests/fixtures/http/openalex_work.json")
    with fixture_path.open() as fp:
        return json.load(fp)


@responses.activate
def test_get_work_normalizes_response(openalex_work_payload: dict) -> None:
    client = OpenAlexClient()
    responses.add(
        responses.GET,
        "https://api.openalex.org/works/W123456789",
        json=openalex_work_payload,
        status=200,
    )

    work = client.get_work("W123456789")

    assert work.openalex_id == "W123456789"
    assert work.doi == "10.5555/example.doi"
    assert work.title == "Example OpenAlex Work"
    assert work.year == 2024
    assert work.venue == "Journal of Testing"
    assert work.abstract == "example openalex abstract text for text"
    assert work.authors == ["Alice Smith", "Bob Jones"]


@responses.activate
def test_search_works_fetches_multiple_results(openalex_work_payload: dict) -> None:
    client = OpenAlexClient()
    second_result = {
        "id": "https://openalex.org/W987654321",
        "doi": None,
        "display_name": "Second Work",
        "publication_year": 2020,
        "host_venue": {"display_name": "Conference of Things"},
        "abstract": "plain abstract text",
        "authorships": [{"author": {"display_name": "Charlie Example"}}],
    }
    payload = {"results": [openalex_work_payload, second_result], "meta": {"next_cursor": "abc123"}}

    responses.add(
        responses.GET,
        "https://api.openalex.org/works",
        json=payload,
        status=200,
    )

    results, cursor = client.search_works("deep learning", per_page=2)

    assert cursor == "abc123"
    assert len(results) == 2

    first, second = results
    assert first.openalex_id == "W123456789"
    assert second.openalex_id == "W987654321"
    assert second.abstract == "plain abstract text"
    assert second.authors == ["Charlie Example"]

    parsed = urlparse(responses.calls[0].request.url)
    params = parse_qs(parsed.query)
    assert params["search"] == ["deep learning"]
    assert params["per-page"] == ["2"]
    assert params["cursor"] == ["*"]


def test_reconstruct_abstract_orders_positions() -> None:
    client = OpenAlexClient()
    abstract = client._reconstruct_abstract({"second": [1], "first": [0], "word": [2], "another": [3]})
    assert abstract == "first second word another"
