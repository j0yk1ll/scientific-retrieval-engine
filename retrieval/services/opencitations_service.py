from __future__ import annotations

from typing import List, Optional

import requests

from .models import Citation


class OpenCitationsService:
    """Minimal client for OpenCitations REST API."""

    BASE_URL = "https://opencitations.net/index/api/v1"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
        base_url: Optional[str] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.base_url = base_url or self.BASE_URL

    def citations(self, paper_id: str) -> List[Citation]:
        if not paper_id:
            return []
        response = self.session.get(
            f"{self.base_url}/citations/{paper_id}", timeout=self.timeout
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return [
            Citation(
                citing=item.get("citing") or "",
                cited=item.get("cited") or "",
                creation=item.get("creation"),
            )
            for item in response.json()
        ]
