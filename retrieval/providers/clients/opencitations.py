"""Client for interacting with the OpenCitations REST API."""

from __future__ import annotations

from typing import List

from retrieval.providers.clients.base import BaseHttpClient, ClientError, NotFoundError
from retrieval.core.identifiers import normalize_doi
from retrieval.core.models import Citation


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
        except (NotFoundError, ClientError):
            return []

        payload = response.json()
        def _normalize_identifier(identifier: str) -> str:
            return normalize_doi(identifier) or (identifier.strip() if identifier else "")

        return [
            Citation(
                citing=_normalize_identifier(item.get("citing")),
                cited=_normalize_identifier(item.get("cited")),
                creation=item.get("creation"),
            )
            for item in payload
        ]
