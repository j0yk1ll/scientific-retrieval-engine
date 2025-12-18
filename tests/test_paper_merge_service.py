from retrieval.models import Paper
from retrieval.services.paper_merge_service import PaperMergeService


def test_merge_prefers_doi_and_tracks_field_sources() -> None:
    crossref_record = Paper(
        paper_id="crossref:1",
        title="Example Title",
        doi="HTTPS://doi.org/10.1000/Example",
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
    assert merged.primary_source == "crossref"
    assert set(merged.provenance.sources) == {"openalex", "crossref"}
    assert merged.provenance.field_sources["abstract"].source == "openalex"
    assert merged.provenance.field_sources["doi"].source == "crossref"
    assert merged.provenance.field_sources["title"].source == "crossref"
    assert merged.provenance.field_sources["paper_id"].source == "crossref"


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


def test_merge_obeys_source_priority_rules() -> None:
    crossref = Paper(
        paper_id="crossref:123",
        title="Priority Title",
        doi="https://doi.org/10.1234/ABC",
        abstract="Short abstract.",
        year=2024,
        venue="Crossref Venue",
        source="crossref",
        url="https://doi.org/10.1234/ABC",
        authors=["Alice"],
    )

    datacite = Paper(
        paper_id="datacite:123",
        title="Priority Title",
        doi="10.1234/abc",
        abstract=None,
        year=2020,
        venue="DataCite Venue",
        source="datacite",
        url="https://datacite.org/10.1234/abc",
        authors=["Alice", "Bob"],
    )

    openalex = Paper(
        paper_id="openalex:W123",
        title="Priority Title",
        doi=None,
        abstract="This is a much longer abstract from OpenAlex for testing priority.",
        year=2021,
        venue="OpenAlex Venue",
        source="openalex",
        url="https://openalex.org/W123",
        authors=["Alice", "Bob"],
    )

    semanticscholar = Paper(
        paper_id="s2:W123",
        title="Priority Title",
        doi=None,
        abstract="Semantic Scholar abstract.",
        year=2022,
        venue="S2 Venue",
        source="semanticscholar",
        url="https://semanticscholar.org/paper/W123",
        authors=["Alice", "Bob", "Charlie", "Dana"],
    )

    merged = PaperMergeService().merge([datacite, openalex, semanticscholar, crossref])

    assert merged.doi == "10.1234/abc"
    assert merged.year == 2024
    assert merged.venue == "Crossref Venue"
    assert merged.url == "https://doi.org/10.1234/ABC"
    assert merged.abstract.startswith("This is a much longer abstract from OpenAlex")
    assert merged.authors == ["Alice", "Bob", "Charlie", "Dana"]
    assert merged.primary_source == "crossref"

    assert merged.provenance.field_sources["doi"].source == "crossref"
    assert merged.provenance.field_sources["year"].source == "crossref"
    assert merged.provenance.field_sources["venue"].source == "crossref"
    assert merged.provenance.field_sources["url"].source == "crossref"
    assert merged.provenance.field_sources["abstract"].source == "openalex"
    assert merged.provenance.field_sources["authors"].source == "semanticscholar"
