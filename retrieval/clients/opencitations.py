"""Client for interacting with the OpenCitations REST API."""

from __future__ import annotations

from typing import List

from retrieval.clients.base import BaseHttpClient, NotFoundError
from retrieval.models import Citation


class OpenCitationsClient(BaseHttpClient):
    """Thin wrapper around the OpenCitations citation lookup API."""

    BASE_URL = "https://opencitations.net/index/api/v1"

    def citations(self, paper_id: str) -> List[Citation]:
        """Return citations for a given paper identifier (e.g., DOI)."""

        if not paper_id:
            return []

        try:
            response = self._request("GET", f"/citations/{paper_id}")
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
