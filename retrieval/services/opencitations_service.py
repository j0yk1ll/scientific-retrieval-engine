from __future__ import annotations

from typing import List, Optional

from retrieval.clients.opencitations import OpenCitationsClient
from retrieval.models import Citation


class OpenCitationsService:
    """Service wrapper around :class:`OpenCitationsClient`."""

    def __init__(self, client: Optional[OpenCitationsClient] = None) -> None:
        self.client = client or OpenCitationsClient()

    def citations(self, paper_id: str) -> List[Citation]:
        """Return citations for the given paper identifier (e.g., DOI)."""

        return self.client.citations(paper_id)
