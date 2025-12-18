from retrieval.models import Paper
from retrieval.services.search_service import PaperSearchService


class StubOpenAlexService:
    def search(self, *args, **kwargs):
        return [], None

    def get_by_doi(self, doi):
        return None


class StubSemanticScholarService:
    def search(self, *args, **kwargs):
        return []

    def get_by_doi(self, doi):
        return None


class StubCrossrefService:
    def __init__(self, *, search_results=None, doi_result=None):
        self._search_results = search_results or []
        self._doi_result = doi_result

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._search_results[:rows]

    def get_by_doi(self, doi):
        return self._doi_result


class StubDataCiteService:
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
    datacite_paper = Paper(
        paper_id="datacite:1",
        title="Deterministic DOI",
        doi="10.1234/missing",
        abstract=None,
        year=2020,
        venue="Data Archive",
        source="datacite",
        url="https://doi.org/10.1234/missing",
        authors=["Alex Example"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexService(),
        semanticscholar=StubSemanticScholarService(),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(doi_result=datacite_paper),
        doi_resolver=StubResolver(),
    )

    results = service.search_by_doi("10.1234/missing")

    assert results[0].source == "datacite"
    assert results[0].doi == "10.1234/missing"


def test_search_by_title_appends_datacite_candidates():
    datacite_candidate = Paper(
        paper_id="datacite-search",
        title="Title Missing Elsewhere",
        doi="10.5555/datacite",
        abstract=None,
        year=2022,
        venue="Repository",
        source="datacite",
        authors=["Pat Lee"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexService(),
        semanticscholar=StubSemanticScholarService(),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(search_results=[datacite_candidate]),
        doi_resolver=StubResolver(),
    )

    results = service.search_by_title("Title Missing Elsewhere", k=3)

    assert datacite_candidate in results
