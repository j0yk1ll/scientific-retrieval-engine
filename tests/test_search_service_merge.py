from retrieval.clients.openalex import OpenAlexWork
from retrieval.clients.semanticscholar import SemanticScholarPaper
from retrieval.services.search_service import PaperSearchService


class StubOpenAlexClient:
    def __init__(self, works):
        self._works = works

    def search_works(self, *args, **kwargs):
        return list(self._works), None


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


def test_search_merges_duplicates_and_exposes_provenance():
    openalex_work = OpenAlexWork(
        openalex_id="W1",
        openalex_url="https://openalex.org/W1",
        doi="10.9999/example",
        title="Merged Paper",
        year=2024,
        venue=None,
        abstract="OpenAlex abstract",
        authors=["Ada Lovelace"],
        referenced_works=[],
    )

    semantics_paper = SemanticScholarPaper(
        paper_id="s2:1",
        doi="10.9999/example",
        title="Merged Paper",
        abstract=None,
        year=2024,
        venue="Conference X",
        url="https://semanticscholar.org/paper/1",
        authors=["Ada Lovelace"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexClient([openalex_work]),
        semanticscholar=StubSemanticScholarClient([semantics_paper]),
        crossref=StubCrossrefClient(),
    )

    merged_results = service.search("merged paper", k=5)

    assert len(merged_results) == 1
    merged = merged_results[0]
    assert merged.doi == "10.9999/example"
    assert merged.abstract == "OpenAlex abstract"
    assert merged.venue == "Conference X"
    assert set(merged.provenance.sources) == {"openalex", "semanticscholar"}
    assert merged.provenance.field_sources["venue"].source == "semanticscholar"

    merged_only, raw_results = service.search_with_raw("merged paper", k=5)
    assert len(raw_results) == 2
    assert merged_only[0].title == "Merged Paper"
