from __future__ import annotations

from typing import Optional

from retrieval.clients.base import ClientError
from retrieval.clients.unpaywall import UnpaywallClient, UnpaywallRecord
from retrieval.models import Paper


class PaperEnrichmentService:
    """Enrich papers with optional metadata from external services."""

    def __init__(self, *, unpaywall_client: Optional[UnpaywallClient] = None) -> None:
        self.unpaywall_client = unpaywall_client

    def enrich(self, paper: Paper) -> Paper:
        """Attempt to enrich a paper with open-access metadata."""

        if not self.unpaywall_client or not paper.doi:
            return paper

        record: Optional[UnpaywallRecord]
        try:
            record = self.unpaywall_client.get_record(paper.doi)
        except (ClientError, ValueError):
            record = None
        if record:
            pdf_url = record.best_pdf_url
            if pdf_url:
                paper.pdf_url = pdf_url
            paper.is_oa = bool(record.best_oa_location or record.oa_locations)
        return paper
