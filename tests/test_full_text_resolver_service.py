from literature_retrieval_engine.core.models import Paper
from literature_retrieval_engine.providers.clients.unpaywall import OpenAccessLocation, UnpaywallRecord
from literature_retrieval_engine.services.full_text_resolver_service import (
    ArxivDeterministicResolver,
    FullTextResolverService,
    UnpaywallResolver,
    UpstreamFieldsResolver,
)


class FakeUnpaywallClient:
    def __init__(self, record: UnpaywallRecord | None) -> None:
        self.record = record

    def get_record(self, doi: str) -> UnpaywallRecord | None:
        return self.record


def test_arxiv_doi_yields_pdf_candidate():
    resolver = ArxivDeterministicResolver()
    paper = Paper(
        paper_id="paper-1",
        title="Sample",
        doi="10.48550/arXiv.2401.12345",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    candidates = resolver.resolve(paper)

    assert [candidate.pdf_url for candidate in candidates] == [
        "https://arxiv.org/pdf/2401.12345.pdf"
    ]


def test_arxiv_landing_url_yields_pdf_candidate():
    resolver = ArxivDeterministicResolver()
    paper = Paper(
        paper_id="paper-2",
        title="Sample",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="test",
        url="https://arxiv.org/abs/2101.00001",
    )

    candidates = resolver.resolve(paper)

    assert [candidate.pdf_url for candidate in candidates] == [
        "https://arxiv.org/pdf/2101.00001.pdf"
    ]


def test_upstream_pdf_url_yields_candidate():
    resolver = UpstreamFieldsResolver()
    paper = Paper(
        paper_id="paper-3",
        title="Sample",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="test",
        pdf_url="https://example.org/paper.pdf",
    )

    candidates = resolver.resolve(paper)

    assert [candidate.pdf_url for candidate in candidates] == [
        "https://example.org/paper.pdf"
    ]


def test_unpaywall_best_location_yields_candidate():
    best_location = OpenAccessLocation(
        url="https://example.org/landing",
        url_for_pdf="https://example.org/best.pdf",
        version="publishedVersion",
        license="cc-by",
        host_type="publisher",
        is_best=True,
    )
    record = UnpaywallRecord(
        doi="10.1234/example",
        title="Sample",
        best_oa_location=best_location,
        oa_locations=[best_location],
    )
    resolver = UnpaywallResolver(FakeUnpaywallClient(record))
    paper = Paper(
        paper_id="paper-4",
        title="Sample",
        doi="10.1234/example",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    candidates = resolver.resolve(paper)

    assert [(candidate.pdf_url, candidate.source) for candidate in candidates] == [
        ("https://example.org/best.pdf", "unpaywall")
    ]
    assert candidates[0].license == "cc-by"
    assert candidates[0].version == "publishedVersion"
    assert candidates[0].host_type == "publisher"
    assert candidates[0].is_best is True


def test_unpaywall_falls_back_to_first_location_when_no_best():
    first_location = OpenAccessLocation(
        url="https://example.org/landing",
        url_for_pdf="https://example.org/first.pdf",
        version="acceptedVersion",
        license=None,
        host_type="repository",
        is_best=False,
    )
    second_location = OpenAccessLocation(
        url="https://example.org/second",
        url_for_pdf="https://example.org/second.pdf",
        version=None,
        license="cc-by-nc",
        host_type="publisher",
        is_best=False,
    )
    record = UnpaywallRecord(
        doi="10.5678/example",
        title="Sample",
        best_oa_location=None,
        oa_locations=[first_location, second_location],
    )
    resolver = UnpaywallResolver(FakeUnpaywallClient(record))
    paper = Paper(
        paper_id="paper-5",
        title="Sample",
        doi="10.5678/example",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    candidates = resolver.resolve(paper)

    assert candidates[0].pdf_url == "https://example.org/first.pdf"
    assert candidates[0].source == "unpaywall"


def test_unpaywall_candidates_order_best_first():
    best_location = OpenAccessLocation(
        url="https://example.org/landing",
        url_for_pdf="https://example.org/best.pdf",
        version="publishedVersion",
        license="cc-by",
        host_type="publisher",
        is_best=True,
    )
    other_location = OpenAccessLocation(
        url="https://example.org/other",
        url_for_pdf="https://example.org/other.pdf",
        version="acceptedVersion",
        license="cc-by-nc",
        host_type="repository",
        is_best=False,
    )
    record = UnpaywallRecord(
        doi="10.9999/example",
        title="Sample",
        best_oa_location=best_location,
        oa_locations=[other_location],
    )
    resolver = UnpaywallResolver(FakeUnpaywallClient(record))
    paper = Paper(
        paper_id="paper-6",
        title="Sample",
        doi="10.9999/example",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    candidates = resolver.resolve(paper)

    assert [candidate.pdf_url for candidate in candidates] == [
        "https://example.org/best.pdf",
        "https://example.org/other.pdf",
    ]


def test_apply_sets_pdf_url_provenance_from_unpaywall_best():
    best_location = OpenAccessLocation(
        url="https://example.org/landing",
        url_for_pdf="https://example.org/best.pdf",
        version="publishedVersion",
        license="cc-by",
        host_type="publisher",
        is_best=True,
    )
    record = UnpaywallRecord(
        doi="10.0000/example",
        title="Sample",
        best_oa_location=best_location,
        oa_locations=[best_location],
    )
    resolver = FullTextResolverService(
        resolvers=[UnpaywallResolver(FakeUnpaywallClient(record))]
    )
    paper = Paper(
        paper_id="paper-7",
        title="Sample",
        doi="10.0000/example",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    resolver.apply(paper)

    assert paper.pdf_url == "https://example.org/best.pdf"
    assert paper.provenance is not None
    assert paper.provenance.field_sources["pdf_url"].source == "unpaywall"


def test_apply_sets_pdf_url_provenance_from_arxiv():
    resolver = FullTextResolverService(resolvers=[ArxivDeterministicResolver()])
    paper = Paper(
        paper_id="paper-8",
        title="Sample",
        doi="10.48550/arXiv.2401.12345",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    resolver.apply(paper)

    assert paper.pdf_url == "https://arxiv.org/pdf/2401.12345.pdf"
    assert paper.provenance is not None
    assert paper.provenance.field_sources["pdf_url"].source == "arxiv"
