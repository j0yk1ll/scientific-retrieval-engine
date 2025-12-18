from retrieval.models import Paper
from retrieval.services.search_service import PaperSearchService


class StubOpenAlexService:
    def __init__(self, papers):
        self._papers = papers

    def search(self, *args, **kwargs):
        return list(self._papers), None


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


def test_search_merges_duplicates_and_exposes_provenance():
    openalex_paper = Paper(
        paper_id="openalex:1",
        title="Merged Paper",
        doi="10.9999/example",
        abstract="OpenAlex abstract",
        year=2024,
        venue=None,
        source="openalex",
        url="https://openalex.org/W1",
        authors=["Ada Lovelace"],
    )

    semantics_paper = Paper(
        paper_id="s2:1",
        title="Merged Paper",
        doi="10.9999/example",
        abstract=None,
        year=2024,
        venue="Conference X",
        source="semanticscholar",
        url="https://semanticscholar.org/paper/1",
        authors=["Ada Lovelace"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexService([openalex_paper]),
        semanticscholar=StubSemanticScholarService([semantics_paper]),
        crossref=StubCrossrefService(),
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
