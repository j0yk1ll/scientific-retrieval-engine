import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from literature_retrieval_engine.core.models import Paper
from literature_retrieval_engine.providers.clients.unpaywall import OpenAccessLocation, UnpaywallRecord
from literature_retrieval_engine.services.paper_enrichment_service import PaperEnrichmentService


class FakeUnpaywallClient:
    def __init__(self, record: UnpaywallRecord | None) -> None:
        self.record = record
        self.requested_doi: str | None = None

    def get_record(self, doi: str) -> UnpaywallRecord | None:
        self.requested_doi = doi
        return self.record


def test_enrich_adds_pdf_and_flags_open_access() -> None:
    record = UnpaywallRecord(
        doi="10.1234/example",
        title="Example",
        best_oa_location=OpenAccessLocation(
            url="https://example.org/landing",
            url_for_pdf="https://example.org/paper.pdf",
            version="publishedVersion",
            license="cc-by",
            host_type="publisher",
            is_best=True,
        ),
        oa_locations=[],
    )
    enrichment = PaperEnrichmentService(unpaywall_client=FakeUnpaywallClient(record))
    paper = Paper(
        paper_id="1",
        title="Example",
        doi="10.1234/example",
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    enriched = enrichment.enrich(paper)

    assert enriched.pdf_url == "https://example.org/paper.pdf"
    assert enriched.is_oa is True


def test_enrich_is_noop_without_doi() -> None:
    enrichment = PaperEnrichmentService(unpaywall_client=FakeUnpaywallClient(None))
    paper = Paper(
        paper_id="1",
        title="No DOI",
        doi=None,
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )

    enriched = enrichment.enrich(paper)

    assert enriched.pdf_url is None
    assert enriched.is_oa is None
