from retrieval.models import Paper
from retrieval.services.search_service import PaperSearchService


class CountingOpenAlexService:
    def __init__(self):
        self.calls = []

    def search(self, query, per_page, min_year=None, max_year=None, cursor=None):
        self.calls.append(cursor)
        if cursor is None:
            return [
                Paper(
                    paper_id="openalex:1",
                    title="First",
                    doi="10.1/first",
                    abstract=None,
                    year=None,
                    venue=None,
                    source="openalex",
                )
            ], "cursor:1"
        return [
            Paper(
                paper_id="openalex:2",
                title="Second",
                doi="10.1/second",
                abstract=None,
                year=None,
                venue=None,
                source="openalex",
            )
        ], None


class StubSemanticScholarService:
    def __init__(self, papers):
        self._papers = papers

    def search(self, *args, **kwargs):
        return list(self._papers)


class StubCrossrefService:
    def search_by_title(self, *args, **kwargs):
        return []

    def get_by_doi(self, doi):
        return None


def test_openalex_default_only_fetches_one_page():
    openalex = CountingOpenAlexService()
    service = PaperSearchService(
        openalex=openalex,
        semanticscholar=StubSemanticScholarService([]),
        crossref=StubCrossrefService(),
    )

    service.search("topic")

    assert len(openalex.calls) == 1
    assert openalex.calls[0] is None


def test_openalex_fetches_extra_pages_when_configured():
    openalex = CountingOpenAlexService()
    service = PaperSearchService(
        openalex=openalex,
        semanticscholar=StubSemanticScholarService([]),
        crossref=StubCrossrefService(),
    )

    merged, raw = service.search_with_raw("topic", openalex_extra_pages=1)

    assert len(openalex.calls) == 2
    assert openalex.calls == [None, "cursor:1"]
    assert len(merged) == 2
    assert len(raw) == 2
