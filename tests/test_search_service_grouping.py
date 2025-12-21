from literature_retrieval_engine.core.models import Paper
from literature_retrieval_engine.providers.clients.openalex import OpenAlexWork
from literature_retrieval_engine.providers.clients.semanticscholar import SemanticScholarPaper
from literature_retrieval_engine.services.search_service import PaperSearchService


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


class StubDataCiteClient(StubCrossrefClient):
    pass


class StubDoiResolver:
    def resolve_doi_from_title(self, *args, **kwargs):
        return None


def test_group_key_does_not_fragment_on_first_author_ordering():
    service = PaperSearchService(
        openalex=StubOpenAlexClient([]),
        semanticscholar=StubSemanticScholarClient([]),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(),
        doi_resolver=StubDoiResolver(),
    )

    canonical_title = "A comprehensive survey of graph transformers and their applications"

    paper_a = Paper(
        paper_id="p1",
        title=canonical_title,
        doi=None,
        abstract=None,
        year=2023,
        venue=None,
        source="openalex",
        authors=["Ada Lovelace", "Grace Hopper"],
    )

    paper_b = Paper(
        paper_id="p2",
        title=canonical_title,
        doi=None,
        abstract=None,
        year=2023,
        venue=None,
        source="semanticscholar",
        authors=["Grace Hopper", "Ada Lovelace"],
    )

    assert service._make_group_key(paper_a) == service._make_group_key(paper_b)


def test_group_key_prefers_doi_like_paper_id_when_missing_doi():
    service = PaperSearchService(
        openalex=StubOpenAlexClient([]),
        semanticscholar=StubSemanticScholarClient([]),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(),
        doi_resolver=StubDoiResolver(),
    )

    paper = Paper(
        paper_id="10.5555/ABC.DEF/1234",
        title=None,
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="openalex",
        authors=None,
    )

    assert service._make_group_key(paper) == "doi:10.5555/abc.def/1234"


def test_soft_grouping_merges_subtitle_punctuation_variants():
    openalex_paper = OpenAlexWork(
        openalex_id="W1",
        openalex_url="https://openalex.org/W1",
        doi=None,
        title="Deep learning: applications in medicine",
        year=2022,
        venue=None,
        abstract=None,
        authors=["Ada Lovelace", "Grace Hopper"],
        referenced_works=[],
    )

    semanticscholar_paper = SemanticScholarPaper(
        paper_id="s2:1",
        doi=None,
        title="Deep learning - applications in medicine",
        abstract=None,
        year=2022,
        venue=None,
        authors=["Ada Lovelace", "Grace Hopper"],
        url=None,
    )

    service = PaperSearchService(
        openalex=StubOpenAlexClient([openalex_paper]),
        semanticscholar=StubSemanticScholarClient([semanticscholar_paper]),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(),
        doi_resolver=StubDoiResolver(),
        enable_soft_grouping=True,
        soft_grouping_threshold=0.8,
    )

    merged, raw = service.search_with_raw("deep learning applications", k=5)

    assert len(raw) == 2
    assert len(merged) == 1
    assert set(merged[0].provenance.sources) == {"openalex", "semanticscholar"}


def test_soft_grouping_merges_minor_word_swaps():
    openalex_paper = OpenAlexWork(
        openalex_id="W2",
        openalex_url="https://openalex.org/W2",
        doi=None,
        title="Efficient transformers for long document classification in medicine",
        year=2022,
        venue=None,
        abstract=None,
        authors=["Ada Lovelace"],
        referenced_works=[],
    )

    semanticscholar_paper = SemanticScholarPaper(
        paper_id="s2:2",
        doi=None,
        title="Efficient transformers for long document classification medicine in",
        abstract=None,
        year=2022,
        venue=None,
        authors=["Ada Lovelace"],
        url=None,
    )

    service = PaperSearchService(
        openalex=StubOpenAlexClient([openalex_paper]),
        semanticscholar=StubSemanticScholarClient([semanticscholar_paper]),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(),
        doi_resolver=StubDoiResolver(),
        enable_soft_grouping=True,
        soft_grouping_threshold=0.82,
    )

    merged, raw = service.search_with_raw("efficient transformers", k=5)

    assert len(raw) == 2
    assert len(merged) == 1


def test_soft_grouping_skips_ambiguous_short_titles():
    openalex_paper = OpenAlexWork(
        openalex_id="W3",
        openalex_url="https://openalex.org/W3",
        doi=None,
        title="AI",
        year=2020,
        venue=None,
        abstract=None,
        authors=["Ada Lovelace"],
        referenced_works=[],
    )

    semanticscholar_paper = SemanticScholarPaper(
        paper_id="s2:3",
        doi=None,
        title="AI",
        abstract=None,
        year=2021,
        venue=None,
        authors=["Grace Hopper"],
        url=None,
    )

    service = PaperSearchService(
        openalex=StubOpenAlexClient([openalex_paper]),
        semanticscholar=StubSemanticScholarClient([semanticscholar_paper]),
        crossref=StubCrossrefClient(),
        datacite=StubDataCiteClient(),
        doi_resolver=StubDoiResolver(),
        enable_soft_grouping=True,
    )

    merged, raw = service.search_with_raw("AI", k=5)

    assert len(raw) == 2
    assert len(merged) == 2
