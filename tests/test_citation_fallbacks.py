from retrieval.api import RetrievalClient
from retrieval.core.models import Citation
from retrieval.core.settings import RetrievalSettings
from retrieval.providers.clients.openalex import OpenAlexWork
from retrieval.providers.clients.semanticscholar import SemanticScholarPaper


class DummyOpenCitationsClient:
    def citations(self, paper_id: str):
        return []


class DummySemanticScholarClient:
    def __init__(self):
        self.calls = []

    def get_citations(self, paper_id: str, *, fields: str = "paperId,externalIds,doi"):
        self.calls.append((paper_id, fields))
        return [
            SemanticScholarPaper(
                paper_id="SS-1",
                doi="10.2000/abc",
                title=None,
                abstract=None,
                year=None,
                venue=None,
                url=None,
                authors=[],
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
        )

    def get_citing_works(self, openalex_work_id: str):
        self.calls.append(("get_citing_works", openalex_work_id))
        return [
            OpenAlexWork(
                openalex_id="W999",
                openalex_url="https://openalex.org/W999",
                doi="10.3000/cite",
                title=None,
                year=None,
                venue=None,
                abstract=None,
                authors=[],
                referenced_works=[],
            )
        ]


def test_search_citations_semanticscholar_fallback():
    settings = RetrievalSettings(enable_semanticscholar_citation_fallback=True)
    client = RetrievalClient(
        settings=settings,
        opencitations_client=DummyOpenCitationsClient(),
        semanticscholar_client=DummySemanticScholarClient(),
    )

    citations = client.search_citations("10.1000/xyz")

    assert citations == [Citation(citing="10.2000/abc", cited="10.1000/xyz", creation=None)]
    assert client._semanticscholar_client.calls[0][0] == "DOI:10.1000/xyz"


def test_search_citations_openalex_fallback():
    settings = RetrievalSettings(enable_openalex_citation_fallback=True)
    client = RetrievalClient(
        settings=settings,
        opencitations_client=DummyOpenCitationsClient(),
        openalex_client=DummyOpenAlexClient(),
    )

    citations = client.search_citations("10.1000/xyz")

    assert citations == [Citation(citing="10.3000/cite", cited="10.1000/xyz", creation=None)]
    assert ("get_work_by_doi", "10.1000/xyz") in client._openalex_client.calls
