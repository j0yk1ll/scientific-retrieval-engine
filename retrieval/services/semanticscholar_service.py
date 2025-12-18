from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .models import Paper


class SemanticScholarService:
    """Client for the Semantic Scholar API (Graph API v1)."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

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

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[Paper]:
        params: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,year,venue,authors,url,doi",
        }
        if min_year is not None:
            params["year"] = f">={min_year}"
        if max_year is not None:
            year_filter = params.get("year")
            if year_filter:
                params["year"] = f"{year_filter},<={max_year}"
            else:
                params["year"] = f"<={max_year}"

        response = self.session.get(
            f"{self.base_url}/paper/search", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        return [self._to_paper(item) for item in data.get("data", [])]

    def get_by_doi(self, doi: str) -> Optional[Paper]:
        if not doi:
            return None
        response = self.session.get(
            f"{self.base_url}/paper/DOI:{doi}",
            params={"fields": "title,abstract,year,venue,authors,url,doi"},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self._to_paper(response.json())

    def get_by_title(self, title: str, *, limit: int = 5) -> List[Paper]:
        return self.search(title, limit=limit)

    def _to_paper(self, payload: Dict[str, Any]) -> Paper:
        authors = [author.get("name", "") for author in payload.get("authors", []) if author.get("name")]
        return Paper(
            paper_id=str(payload.get("paperId") or payload.get("externalIds", {}).get("CorpusId") or payload.get("doi") or payload.get("title") or ""),
            title=payload.get("title") or "",
            doi=payload.get("doi"),
            abstract=payload.get("abstract"),
            year=payload.get("year"),
            venue=payload.get("venue"),
            source="semanticscholar",
            url=payload.get("url"),
            authors=authors,
        )
