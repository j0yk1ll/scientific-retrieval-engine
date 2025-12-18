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


def test_merge_prefers_higher_priority_source_for_doi() -> None:
    datacite = Paper(
        paper_id="datacite:1",
        title="Example",
        doi="10.9999/example",
        abstract="",
        year=2024,
        venue="",
        source="datacite",
    )

    crossref = Paper(
        paper_id="crossref:1",
        title="Example",
        doi="HTTPS://doi.org/10.9999/example",
        abstract=None,
        year=2024,
        venue="",
        source="crossref",
    )

    merged = PaperMergeService().merge([datacite, crossref])

    assert merged.doi == "10.9999/example"
    assert merged.primary_source == "crossref"
    assert merged.provenance.field_sources["doi"].source == "crossref"


def test_primary_source_prefers_doi_presence_over_priority() -> None:
    higher_priority_without_doi = Paper(
        paper_id="datacite:1",
        title="Example",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="datacite",
    )

    lower_priority_with_doi = Paper(
        paper_id="crossref:1",
        title="Example",
        doi="10.1234/example",
        abstract=None,
        year=None,
        venue=None,
        source="crossref",
    )

    merged = PaperMergeService(source_priority=["datacite", "crossref"]).merge(
        [higher_priority_without_doi, lower_priority_with_doi]
    )

    assert merged.primary_source == "crossref"
    assert merged.doi == "10.1234/example"
    assert merged.provenance.field_sources["doi"].source == "crossref"


def test_merge_tie_breaker_abstract_prefers_longer() -> None:
    secondary = Paper(
        paper_id="secondary",
        title="Example",
        doi=None,
        abstract="Short abstract.",
        year=None,
        venue=None,
        source="secondary",
    )

    primary = Paper(
        paper_id="primary",
        title="Example",
        doi=None,
        abstract="This is a much longer abstract used for tie breaking.",
        year=None,
        venue=None,
        source="primary",
    )

    merged = PaperMergeService().merge([secondary, primary])

    assert merged.abstract == "This is a much longer abstract used for tie breaking."
    assert merged.provenance.field_sources["abstract"].source == "primary"


def test_merge_authors_tie_breaker_prefers_more_authors() -> None:
    openalex = Paper(
        paper_id="openalex:1",
        title="Example",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="openalex",
        authors=["Alice"],
    )

    semanticscholar = Paper(
        paper_id="s2:1",
        title="Example",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="semanticscholar",
        authors=["Alice", "Bob"],
    )

    merged = PaperMergeService().merge([openalex, semanticscholar])

    assert merged.authors == ["Alice", "Bob"]
    assert merged.provenance.field_sources["authors"].source == "semanticscholar"


def test_merge_respects_custom_source_priority_for_key_fields() -> None:
    crossref = Paper(
        paper_id="crossref:doi",
        title="Example",
        doi="10.1000/custom",
        abstract=None,
        year=2024,
        venue="Crossref Venue",
        source="crossref",
    )

    openalex = Paper(
        paper_id="openalex:doi",
        title="Example",
        doi="10.1000/custom",
        abstract=None,
        year=2023,
        venue="OpenAlex Venue",
        source="openalex",
    )

    merged = PaperMergeService(source_priority=["openalex", "crossref"]).merge(
        [crossref, openalex]
    )

    assert merged.doi == "10.1000/custom"
    assert merged.year == 2023
    assert merged.venue == "OpenAlex Venue"
    assert merged.provenance.field_sources["year"].source == "openalex"
    assert merged.provenance.field_sources["venue"].source == "openalex"


def test_merge_default_priority_is_preserved_for_key_fields() -> None:
    crossref = Paper(
        paper_id="crossref:doi",
        title="Example",
        doi="10.1000/default",
        abstract=None,
        year=2025,
        venue="Crossref Venue",
        source="crossref",
    )

    openalex = Paper(
        paper_id="openalex:doi",
        title="Example",
        doi="10.1000/default",
        abstract=None,
        year=2024,
        venue="OpenAlex Venue",
        source="openalex",
    )

    merged = PaperMergeService().merge([crossref, openalex])

    assert merged.doi == "10.1000/default"
    assert merged.year == 2025
    assert merged.venue == "Crossref Venue"
    assert merged.provenance.field_sources["year"].source == "crossref"
    assert merged.provenance.field_sources["venue"].source == "crossref"


def test_primary_source_when_no_doi_uses_title_evidence_or_rule() -> None:
    crossref = Paper(
        paper_id="crossref:1",
        title="",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="crossref",
    )

    openalex = Paper(
        paper_id="openalex:1",
        title="Determined Title",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="openalex",
    )

    merged = PaperMergeService().merge([crossref, openalex])

    assert merged.title == "Determined Title"
    assert merged.primary_source == "openalex"
    assert merged.provenance.field_sources["title"].source == "openalex"


def test_tie_handling_updates_selected_evidence() -> None:
    first = Paper(
        paper_id="p1",
        title="Example",
        doi=None,
        abstract="Short",
        year=None,
        venue=None,
        source="unknown",
    )

    second = Paper(
        paper_id="p2",
        title="Example",
        doi=None,
        abstract="Longer abstract text",  # wins tie breaker
        year=None,
        venue=None,
        source="unknown",
    )

    third = Paper(
        paper_id="p3",
        title="Example",
        doi=None,
        abstract="Longest abstract text so far",  # should win after second
        year=None,
        venue=None,
        source="unknown",
    )

    merged = PaperMergeService().merge([first, second, third])

    assert merged.abstract == "Longest abstract text so far"
    assert merged.provenance.field_sources["abstract"].source == "unknown"


def test_primary_source_prefers_identifier_evidence_over_other_fields() -> None:
    crossref = Paper(
        paper_id="crossref:10",
        title="",
        doi="10.4321/primary",
        abstract=None,
        year=None,
        venue=None,
        source="crossref",
    )

    openalex = Paper(
        paper_id="openalex:10",
        title="Fresh and Improved Title",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="openalex",
    )

    merged = PaperMergeService().merge([openalex, crossref])

    assert merged.title == "Fresh and Improved Title"
    assert merged.primary_source == "crossref"
    assert merged.provenance.field_sources["title"].source == "openalex"
