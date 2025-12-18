"""Client for interacting with the OpenCitations REST API."""

from __future__ import annotations

from typing import List

from retrieval.clients.base import BaseHttpClient, NotFoundError
from retrieval.identifiers import normalize_doi
from retrieval.models import Citation


class OpenCitationsClient(BaseHttpClient):
    """Thin wrapper around the OpenCitations citation lookup API."""

    BASE_URL = "https://opencitations.net/index/api/v1"

    def citations(self, paper_id: str) -> List[Citation]:
        """Return citations for a given paper identifier (e.g., DOI).

        DOI-like strings are normalized before being sent to OpenCitations.
        """

        normalized_paper_id = normalize_doi(paper_id) or (paper_id.strip() if paper_id else "")
        if not normalized_paper_id:
            return []

        try:
            response = self._request("GET", f"/citations/{normalized_paper_id}")
        except NotFoundError:
            return []

        payload = response.json()
        return [
            Citation(
                citing=item.get("citing") or "",
                cited=item.get("cited") or "",
                creation=item.get("creation"),
            )
            for item in payload
        ]
