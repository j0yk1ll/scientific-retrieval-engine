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


class StubDataCiteService(StubCrossrefService):
    pass


class StubDoiResolver:
    def resolve_doi_from_title(self, *args, **kwargs):
        return None


def test_group_key_does_not_fragment_on_first_author_ordering():
    service = PaperSearchService(
        openalex=StubOpenAlexService([]),
        semanticscholar=StubSemanticScholarService([]),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(),
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
        openalex=StubOpenAlexService([]),
        semanticscholar=StubSemanticScholarService([]),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(),
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
    openalex_paper = Paper(
        paper_id="oa:1",
        title="Deep learning: applications in medicine",
        doi=None,
        abstract=None,
        year=2022,
        venue=None,
        source="openalex",
        authors=["Ada Lovelace", "Grace Hopper"],
    )

    semanticscholar_paper = Paper(
        paper_id="s2:1",
        title="Deep learning - applications in medicine",
        doi=None,
        abstract=None,
        year=2022,
        venue=None,
        source="semanticscholar",
        authors=["Ada Lovelace", "Grace Hopper"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexService([openalex_paper]),
        semanticscholar=StubSemanticScholarService([semanticscholar_paper]),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(),
        doi_resolver=StubDoiResolver(),
        enable_soft_grouping=True,
        soft_grouping_threshold=0.8,
    )

    merged, raw = service.search_with_raw("deep learning applications", k=5)

    assert len(raw) == 2
    assert len(merged) == 1
    assert set(merged[0].provenance.sources) == {"openalex", "semanticscholar"}


def test_soft_grouping_merges_minor_word_swaps():
    openalex_paper = Paper(
        paper_id="oa:2",
        title="Efficient transformers for long document classification in medicine",
        doi=None,
        abstract=None,
        year=2022,
        venue=None,
        source="openalex",
        authors=["Ada Lovelace"],
    )

    semanticscholar_paper = Paper(
        paper_id="s2:2",
        title="Efficient transformers for long document classification medicine in",
        doi=None,
        abstract=None,
        year=2022,
        venue=None,
        source="semanticscholar",
        authors=["Ada Lovelace"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexService([openalex_paper]),
        semanticscholar=StubSemanticScholarService([semanticscholar_paper]),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(),
        doi_resolver=StubDoiResolver(),
        enable_soft_grouping=True,
        soft_grouping_threshold=0.82,
    )

    merged, raw = service.search_with_raw("efficient transformers", k=5)

    assert len(raw) == 2
    assert len(merged) == 1


def test_soft_grouping_skips_ambiguous_short_titles():
    openalex_paper = Paper(
        paper_id="oa:3",
        title="AI",
        doi=None,
        abstract=None,
        year=2020,
        venue=None,
        source="openalex",
        authors=["Ada Lovelace"],
    )

    semanticscholar_paper = Paper(
        paper_id="s2:3",
        title="AI",
        doi=None,
        abstract=None,
        year=2021,
        venue=None,
        source="semanticscholar",
        authors=["Grace Hopper"],
    )

    service = PaperSearchService(
        openalex=StubOpenAlexService([openalex_paper]),
        semanticscholar=StubSemanticScholarService([semanticscholar_paper]),
        crossref=StubCrossrefService(),
        datacite=StubDataCiteService(),
        doi_resolver=StubDoiResolver(),
        enable_soft_grouping=True,
    )

    merged, raw = service.search_with_raw("AI", k=5)

    assert len(raw) == 2
    assert len(merged) == 2
