from literature_retrieval_engine.providers.clients.crossref import CrossrefWork
from literature_retrieval_engine.providers.clients.openalex import OpenAlexWork
from literature_retrieval_engine.services.search_service import PaperSearchService


class StubOpenAlexClient:
    def __init__(self, works):
        self._works = works

    def search_works(self, *args, **kwargs):
        return self._works, None

    def get_work_by_doi(self, doi):
        return None


class StubSemanticScholarClient:
    def __init__(self, papers):
        self._papers = papers

    def search_papers(self, *args, **kwargs):
        return list(self._papers)

    def get_by_doi(self, doi, **kwargs):
        return None


class StubCrossrefClient:
    def __init__(self, *, search_results, doi_result=None):
        self._search_results = search_results
        self._doi_result = doi_result

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._search_results[:rows]

    def works_by_doi(self, doi):
        return self._doi_result


def test_search_by_title_resolves_missing_doi_and_upgrades_metadata():
    missing_doi_paper = OpenAlexWork(
        openalex_id="W1",
        openalex_url="https://openalex.org/W1",
        doi=None,
        title="Deterministic Title",
        abstract=None,
        year=None,
        venue=None,
        authors=["Casey Smith"],
        referenced_works=[],
    )

    canonical_paper = CrossrefWork(
        doi="10.5555/deterministic",
        title="Deterministic Title",
        year=2021,
        venue="Journal of Tests",
        url="https://doi.org/10.5555/deterministic",
        authors=["Casey Smith"],
    )

    crossref_search_results = [
        CrossrefWork(
            doi="10.5555/deterministic",
            title="Deterministic Title",
            year=2021,
            venue=None,
            authors=["Casey Smith"],
            url=None,
        )
    ]

    service = PaperSearchService(
        openalex=StubOpenAlexClient([missing_doi_paper]),
        semanticscholar=StubSemanticScholarClient([]),
        crossref=StubCrossrefClient(search_results=crossref_search_results, doi_result=canonical_paper),
    )

    results = service.search_by_title("Deterministic Title")

    assert results[0].doi == "10.5555/deterministic"
    assert results[0].source == "crossref"
    assert results[0].year == 2021
