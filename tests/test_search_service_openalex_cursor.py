from retrieval.providers.clients.openalex import OpenAlexWork
from retrieval.services.search_service import PaperSearchService


class CountingOpenAlexClient:
    def __init__(self):
        self.calls = []

    def search_works(self, query, per_page, min_year=None, max_year=None, cursor=None, filters=None):
        self.calls.append(cursor)
        if cursor == "*":
            return [
                OpenAlexWork(
                    openalex_id="W1",
                    openalex_url="https://openalex.org/W1",
                    doi="10.1/first",
                    title="First",
                    abstract=None,
                    year=None,
                    venue=None,
                    authors=[],
                    referenced_works=[],
                )
            ], "cursor:1"
        return [
            OpenAlexWork(
                openalex_id="W2",
                openalex_url="https://openalex.org/W2",
                doi="10.1/second",
                title="Second",
                abstract=None,
                year=None,
                venue=None,
                authors=[],
                referenced_works=[],
            )
        ], None


class StubSemanticScholarClient:
    def __init__(self, papers):
        self._papers = papers

    def search_papers(self, *args, **kwargs):
        return list(self._papers)


class StubCrossrefClient:
    def search_by_title(self, *args, **kwargs):
        return []

    def works_by_doi(self, doi):
        return None


def test_openalex_default_only_fetches_one_page():
    openalex = CountingOpenAlexClient()
    service = PaperSearchService(
        openalex=openalex,
        semanticscholar=StubSemanticScholarClient([]),
        crossref=StubCrossrefClient(),
    )

    service.search("topic")

    assert len(openalex.calls) == 1
    assert openalex.calls[0] == "*"


def test_openalex_fetches_extra_pages_when_configured():
    openalex = CountingOpenAlexClient()
    service = PaperSearchService(
        openalex=openalex,
        semanticscholar=StubSemanticScholarClient([]),
        crossref=StubCrossrefClient(),
    )

    merged, raw = service.search_with_raw("topic", openalex_extra_pages=1)

    assert len(openalex.calls) == 2
    assert openalex.calls == ["*", "cursor:1"]
    assert len(merged) == 2
    assert len(raw) == 2
