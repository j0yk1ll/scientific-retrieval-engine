from retrieval.models import Paper
from retrieval.services.doi_resolver_service import DoiResolverService


class StubCrossrefService:
    def __init__(self, papers):
        self._papers = papers

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._papers[:rows]


class StubDataCiteService:
    def __init__(self, papers):
        self._papers = papers

    def search_by_title(self, title, *, rows=5, from_year=None, until_year=None):
        return self._papers[:rows]


def test_resolve_uses_title_match_and_author_overlap():
    title = "A Precise Study"
    papers = [
        Paper(
            paper_id="1",
            title=title,
            doi="10.1111/title-match",
            abstract=None,
            year=2020,
            venue=None,
            source="crossref",
            authors=["Alice Smith"],
        ),
        Paper(
            paper_id="2",
            title=title,
            doi="10.2222/wrong-author",
            abstract=None,
            year=2020,
            venue=None,
            source="crossref",
            authors=["Bob Jones"],
        ),
    ]

    resolver = DoiResolverService(
        crossref=StubCrossrefService(papers), datacite=StubDataCiteService([])
    )

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Alice Smith"])

    assert resolved == "10.1111/title-match"


def test_resolve_falls_back_to_datacite_when_crossref_missing():
    title = "A Precise Study"
    crossref_papers: list[Paper] = []
    datacite_papers = [
        Paper(
            paper_id="datacite-1",
            title=title,
            doi="10.9999/datacite",
            abstract=None,
            year=2021,
            venue=None,
            source="datacite",
            authors=["Dana Scully"],
        )
    ]

    resolver = DoiResolverService(
        crossref=StubCrossrefService(crossref_papers), datacite=StubDataCiteService(datacite_papers)
    )

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Dana Scully"])

    assert resolved == "10.9999/datacite"
