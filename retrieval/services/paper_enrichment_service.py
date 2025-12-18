from __future__ import annotations

from typing import Optional

from retrieval.models import Paper
from retrieval.services.unpaywall_service import UnpaywallService


class PaperEnrichmentService:
    """Enrich papers with optional metadata from external services."""

    def __init__(self, *, unpaywall: Optional[UnpaywallService] = None) -> None:
        self.unpaywall = unpaywall

    def enrich(self, paper: Paper) -> Paper:
        """Attempt to enrich a paper with open-access metadata."""

        if not self.unpaywall or not paper.doi:
            return paper

        record = self.unpaywall.get_record(paper.doi)
        if record:
            pdf_url = record.best_pdf_url
            if pdf_url:
                paper.pdf_url = pdf_url
            paper.is_oa = bool(record.best_oa_location or record.oa_locations)
        return paper
