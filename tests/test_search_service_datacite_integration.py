from retrieval.clients.datacite import DataCiteWork
from retrieval.services.search_service import PaperSearchService


class StubOpenAlexClient:
    def search_works(self, *args, **kwargs):
        return [], None

    def get_work_by_doi(self, doi):
        return None


class StubSemanticScholarClient:
    def search_papers(self, *args, **kwargs):
        return []

    def get_by_doi(self, doi, **kwargs):
        return None


class StubCrossrefClient:
    def __init__(self, *, search_results=None, doi_result=None):
        self._search_results = search_results or []
        self._doi_result = doi_result

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._search_results[:rows]

    def works_by_doi(self, doi):
        return self._doi_result


class StubDataCiteClient:
    def __init__(self, *, search_results=None, doi_result=None):
        self._search_results = search_results or []
        self._doi_result = doi_result

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._search_results[:rows]

    def get_by_doi(self, doi):
        return self._doi_result


class StubResolver:
    def resolve_doi_from_title(self, title, expected_authors=None):
        return None


def test_search_by_doi_returns_datacite_when_primary_sources_missing():
    datacite_paper = DataCiteWork(
        title="Deterministic DOI",
        doi="10.1234/missing",
        year=2020,
        venue="Data Archive",
        url="https://doi.org/10.1234/missing",
        authors=["Alex Example"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexClient(),
        semanticscholar=StubSemanticScholarClient(),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(doi_result=datacite_paper),
        doi_resolver=StubResolver(),
    )

    results = service.search_by_doi("10.1234/missing")

    assert results[0].source == "datacite"
    assert results[0].doi == "10.1234/missing"


def test_search_by_title_appends_datacite_candidates():
    datacite_candidate = DataCiteWork(
        title="Title Missing Elsewhere",
        doi="10.5555/datacite",
        year=2022,
        venue="Repository",
        authors=["Pat Lee"],
        url=None,
    )

    service = PaperSearchService(
        openalex=StubOpenAlexClient(),
        semanticscholar=StubSemanticScholarClient(),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(search_results=[datacite_candidate]),
        doi_resolver=StubResolver(),
    )

    results = service.search_by_title("Title Missing Elsewhere", k=3)

    assert any(result.doi == "10.5555/datacite" and result.source == "datacite" for result in results)
