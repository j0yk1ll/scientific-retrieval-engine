from retrieval.models import Paper
from retrieval.services.doi_resolver_service import DoiResolverService


class StubCrossrefService:
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

    resolver = DoiResolverService(crossref=StubCrossrefService(papers))

    resolved = resolver.resolve_doi_from_title(title, expected_authors=["Alice Smith"])

    assert resolved == "10.1111/title-match"
