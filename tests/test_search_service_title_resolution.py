from retrieval.models import Paper
from retrieval.services.search_service import PaperSearchService


class StubOpenAlexService:
    def __init__(self, papers):
        self._papers = papers

    def search(self, *args, **kwargs):
        return self._papers, None

    def get_by_doi(self, doi):
        return None


class StubSemanticScholarService:
    def __init__(self, papers):
        self._papers = papers

    def search(self, *args, **kwargs):
        return list(self._papers)

    def get_by_doi(self, doi):
        return None


class StubCrossrefService:
    def __init__(self, *, search_results, doi_result=None):
        self._search_results = search_results
        self._doi_result = doi_result

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._search_results[:rows]

    def get_by_doi(self, doi):
        return self._doi_result


def test_search_by_title_resolves_missing_doi_and_upgrades_metadata():
    missing_doi_paper = Paper(
        paper_id="openalex:1",
        title="Deterministic Title",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="openalex",
        authors=["Casey Smith"],
    )

    canonical_paper = Paper(
        paper_id="crossref:deterministic",
        title="Deterministic Title",
        doi="10.5555/deterministic",
        abstract=None,
        year=2021,
        venue="Journal of Tests",
        source="crossref",
        url="https://doi.org/10.5555/deterministic",
        authors=["Casey Smith"],
    )

    crossref_search_results = [
        Paper(
            paper_id="crossref-search",
            title="Deterministic Title",
            doi="10.5555/deterministic",
            abstract=None,
            year=2021,
            venue=None,
            source="crossref",
            authors=["Casey Smith"],
        )
    ]

    service = PaperSearchService(
        openalex=StubOpenAlexService([missing_doi_paper]),
        semanticscholar=StubSemanticScholarService([]),
        crossref=StubCrossrefService(search_results=crossref_search_results, doi_result=canonical_paper),
    )

    results = service.search_by_title("Deterministic Title")

    assert results[0].doi == "10.5555/deterministic"
    assert results[0].source == "crossref"
    assert results[0].year == 2021
