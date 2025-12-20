from retrieval.core.models import Paper
from retrieval.services.full_text_resolver_service import (
    ArxivDeterministicResolver,
    UpstreamFieldsResolver,
)


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
