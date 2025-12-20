from retrieval.api import RetrievalClient
from retrieval.core.models import Paper
from retrieval.core.settings import RetrievalSettings
from retrieval.providers.clients.openalex import OpenAlexWork
from retrieval.providers.clients.semanticscholar import SemanticScholarPaper


class DummyOpenAlexClientNoResults:
    def __init__(self):
        self.calls = []

    def get_work_by_doi(self, doi: str):
        self.calls.append(("get_work_by_doi", doi))
        return None

    def get_citing_works(self, openalex_work_id: str, *, max_pages: int = 5):
        self.calls.append(("get_citing_works", openalex_work_id, max_pages))
        return []


class DummySemanticScholarClient:
    def __init__(self):
        self.calls = []

    def get_by_doi(self, doi: str, *, fields: str):
        self.calls.append(("get_by_doi", doi, fields))
        return SemanticScholarPaper(
            paper_id="SS-SEED",
            doi=doi,
            title="Seed Paper",
            abstract=None,
            year=2021,
            venue=None,
            url=None,
            pdf_url=None,
            authors=[],
        )

    def get_citations(
        self,
        paper_id: str,
        *,
        fields: str = "paperId,externalIds,doi",
        limit: int = 500,
    ):
        self.calls.append((paper_id, fields, limit))
        return [
            SemanticScholarPaper(
                paper_id="SS-1",
                doi="10.2000/abc",
                title="Semantic Scholar Citing Paper",
                abstract=None,
                year=2020,
                venue=None,
                url=None,
                authors=[],
                pdf_url=None,
            )
        ]


class DummyOpenAlexClient:
    def __init__(self):
        self.calls = []

    def get_work_by_doi(self, doi: str):
        self.calls.append(("get_work_by_doi", doi))
        return OpenAlexWork(
            openalex_id="W123",
            openalex_url="https://openalex.org/W123",
            doi=doi,
            title=None,
            year=None,
            venue=None,
            abstract=None,
            authors=[],
            referenced_works=[],
            pdf_url=None,
            is_oa=None,
        )

    def get_citing_works(self, openalex_work_id: str, *, max_pages: int = 5):
        self.calls.append(("get_citing_works", openalex_work_id, max_pages))
        return [
            OpenAlexWork(
                openalex_id="W999",
                openalex_url="https://openalex.org/W999",
                doi="10.3000/cite",
                title="OpenAlex Citing Paper",
                year=2019,
                venue=None,
                abstract=None,
                authors=[],
                referenced_works=[],
                pdf_url=None,
                is_oa=None,
            )
        ]


def test_search_citations_semanticscholar_fallback():
    settings = RetrievalSettings(enable_semanticscholar_citation_fallback=True)
    client = RetrievalClient(
        settings=settings,
        openalex_client=DummyOpenAlexClientNoResults(),
        semanticscholar_client=DummySemanticScholarClient(),
    )

    citations = client.search_citations("10.1000/xyz")

    assert citations == [
        Paper(
            paper_id="SS-1",
            title="Semantic Scholar Citing Paper",
            doi="10.2000/abc",
            abstract=None,
            year=2020,
            venue=None,
            source="semanticscholar",
            url=None,
            pdf_url=None,
            is_oa=False,
            authors=[],
        )
    ]
    assert client._semanticscholar_client.calls[1][0] == "DOI:10.1000/xyz"


def test_search_citations_openalex_fallback():
    settings = RetrievalSettings(enable_openalex_citation_fallback=True)
    client = RetrievalClient(
        settings=settings,
        openalex_client=DummyOpenAlexClient(),
        semanticscholar_client=DummySemanticScholarClient(),
    )

    citations = client.search_citations("10.1000/xyz")

    assert citations == [
        Paper(
            paper_id="W999",
            title="OpenAlex Citing Paper",
            doi="10.3000/cite",
            abstract=None,
            year=2019,
            venue=None,
            source="openalex",
            url="https://openalex.org/W999",
            pdf_url=None,
            is_oa=None,
            authors=[],
        )
    ]
    assert ("get_work_by_doi", "10.1000/xyz") in client._openalex_client.calls
