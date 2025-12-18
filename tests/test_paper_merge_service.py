from retrieval.models import Paper
from retrieval.services.paper_merge_service import PaperMergeService


def test_merge_prefers_doi_and_tracks_field_sources() -> None:
    crossref_record = Paper(
        paper_id="crossref:1",
        title="Example Title",
        doi="10.1000/example",
        abstract=None,
        year=2020,
        venue="Journal A",
        source="crossref",
        url="https://doi.org/10.1000/example",
        authors=["Ada Lovelace"],
    )

    openalex_record = Paper(
        paper_id="openalex:W1",
        title="Example Title",
        doi=None,
        abstract="Rich abstract from OpenAlex.",
        year=2020,
        venue="Journal A",
        source="openalex",
        url="https://openalex.org/W1",
        authors=["Ada Lovelace"],
    )

    merge_service = PaperMergeService()

    merged = merge_service.merge([openalex_record, crossref_record])

    assert merged.doi == "10.1000/example"
    assert merged.abstract == "Rich abstract from OpenAlex."
    assert merged.source == "crossref"
    assert set(merged.provenance.sources) == {"openalex", "crossref"}
    assert merged.provenance.field_sources["abstract"].source == "openalex"
    assert merged.provenance.field_sources["doi"].source == "crossref"


def test_merge_uses_authors_from_best_available_record() -> None:
    primary = Paper(
        paper_id="primary",
        title="Example",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="semanticscholar",
        authors=[],
    )

    secondary = Paper(
        paper_id="secondary",
        title="Example",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="openalex",
        authors=["Grace Hopper"],
    )

    merged = PaperMergeService().merge([primary, secondary])

    assert merged.authors == ["Grace Hopper"]
    assert merged.provenance.field_sources["authors"].source == "openalex"
