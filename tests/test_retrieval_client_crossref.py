import requests

from retrieval.api import RetrievalClient
from retrieval.core.settings import RetrievalSettings
from retrieval.providers.clients.crossref import CrossrefClient
from retrieval.providers.clients.openalex import OpenAlexClient
from retrieval.providers.clients.semanticscholar import SemanticScholarClient


def test_crossref_client_uses_shared_session(monkeypatch):
    session = requests.Session()
    session.headers["User-Agent"] = "custom-agent"

    settings = RetrievalSettings(timeout=1.23, user_agent="custom-agent")
    captured: dict[str, object] = {}

    def fake_request(self, method, path, **kwargs):  # type: ignore[override]
        captured["session_id"] = id(self.session)
        captured["user_agent"] = self.session.headers.get("User-Agent")

        class DummyResponse:
            status_code = 200

            @staticmethod
            def json():
                return {"message": {"items": []}}

        return DummyResponse()

    monkeypatch.setattr(CrossrefClient, "_request", fake_request)
    monkeypatch.setattr(
        OpenAlexClient, "search_works", lambda self, *a, **k: ([], None)
    )
    monkeypatch.setattr(
        SemanticScholarClient,
        "search_papers",
        lambda self, *a, **k: [],
    )

    client = RetrievalClient(settings=settings, session=session)
    client.search_paper_by_title("Example")

    assert captured["session_id"] == id(session)
    assert captured["user_agent"] == "custom-agent"


def test_search_by_title_smoke(monkeypatch):
    def fake_request(self, method, path, **kwargs):  # type: ignore[override]
        class DummyResponse:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "message": {
                        "items": [
                            {
                                "DOI": "10.1111/example",
                                "title": ["Synthetic result"],
                                "author": [{"given": "Ada", "family": "Lovelace"}],
                                "issued": {"date-parts": [[2024, 1, 1]]},
                                "container-title": ["Journal of Tests"],
                                "URL": "https://example.org/doi/10.1111/example",
                            }
                        ]
                    }
                }

        return DummyResponse()

    monkeypatch.setattr(CrossrefClient, "_request", fake_request)
    monkeypatch.setattr(
        OpenAlexClient, "search_works", lambda self, *a, **k: ([], None)
    )
    monkeypatch.setattr(
        SemanticScholarClient,
        "search_papers",
        lambda self, *a, **k: [],
    )

    client = RetrievalClient()
    papers = client.search_paper_by_title("Synthetic result")

    assert papers
    assert papers[0].source == "crossref"
