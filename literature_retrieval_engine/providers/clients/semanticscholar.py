"""Semantic Scholar client for metadata discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from literature_retrieval_engine.core.identifiers import normalize_doi
from literature_retrieval_engine.providers.clients.base import (
    BaseHttpClient,
    NotFoundError,
    RateLimitedError,
    RequestRejectedError,
)

DEFAULT_FIELDS = "paperId,externalIds,title,abstract,year,venue,authors.name,url,openAccessPdf"


@dataclass
class SemanticScholarPaper:
    """Normalized representation of a Semantic Scholar paper."""

    paper_id: str
    doi: Optional[str]
    title: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    url: Optional[str]
    pdf_url: Optional[str]
    authors: List[str]


class SemanticScholarClient(BaseHttpClient):
    """Lightweight wrapper around the Semantic Scholar Graph API v1."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        debug_logging: bool = False,
    ) -> None:
        super().__init__(
            session=session,
            base_url=base_url,
            timeout=timeout,
            debug_logging=debug_logging,
        )
        self.api_key = api_key

    def _auth_headers(self) -> Optional[Dict[str, str]]:
        if not self.api_key:
            return None
        return {"x-api-key": self.api_key}

    def search_papers(
        self,
        query: str,
        *,
        limit: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fields: str = DEFAULT_FIELDS,
    ) -> List[SemanticScholarPaper]:
        params: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "fields": fields,
        }

        year_filters: List[str] = []
        if min_year is not None:
            year_filters.append(f">={min_year}")
        if max_year is not None:
            year_filters.append(f"<={max_year}")
        if year_filters:
            params["year"] = ",".join(year_filters)

        response = self._request(
            "GET", "/paper/search", params=params, headers=self._auth_headers()
        )
        payload = response.json()
        return [self._normalize_paper(item) for item in payload.get("data", []) if isinstance(item, dict)]

    def search_papers_advanced(
        self,
        query: str,
        *,
        limit: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        fields: str = DEFAULT_FIELDS,
    ) -> List[SemanticScholarPaper]:
        payload: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "fields": fields,
        }

        year_filters: List[str] = []
        if min_year is not None:
            year_filters.append(f">={min_year}")
        if max_year is not None:
            year_filters.append(f"<={max_year}")
        if year_filters:
            payload["year"] = ",".join(year_filters)

        try:
            response = self._request(
                "POST", "/paper/search/bulk", json=payload, headers=self._auth_headers()
            )
        except (NotFoundError, RateLimitedError, RequestRejectedError):
            return self.search_papers(
                query,
                limit=limit,
                min_year=min_year,
                max_year=max_year,
                fields=fields,
            )

        data = response.json()
        return [self._normalize_paper(item) for item in data.get("data", []) if isinstance(item, dict)]

    def get_by_doi(
        self, doi: str, *, fields: str = DEFAULT_FIELDS
    ) -> Optional[SemanticScholarPaper]:
        normalized_doi = normalize_doi(doi)
        if not normalized_doi:
            return None

        try:
            response = self._request(
                "GET",
                f"/paper/DOI:{normalized_doi}",
                params={"fields": fields},
                headers=self._auth_headers(),
            )
        except NotFoundError:
            return None

        return self._normalize_paper(response.json())

    def get_citations(
        self,
        paper_id: str,
        *,
        limit: int = 500,
        page_size: int = 100,
    ) -> List[SemanticScholarPaper]:
        if not paper_id:
            return []

        fields = ",".join(
            [
                "citingPaper.paperId",
                "citingPaper.externalIds",
                "citingPaper.title",
                "citingPaper.abstract",
                "citingPaper.year",
                "citingPaper.venue",
                "citingPaper.authors.name",
                "citingPaper.url",
                "citingPaper.openAccessPdf",
            ]
        )

        results: List[SemanticScholarPaper] = []
        offset = 0
        page_size = max(1, min(page_size, 1000))
        limit = max(1, limit)

        while len(results) < limit:
            response = self._request(
                "GET",
                f"/paper/{paper_id}/citations",
                params={
                    "fields": fields,
                    "limit": min(page_size, limit - len(results)),
                    "offset": offset,
                },
                headers=self._auth_headers(),
            )
            payload = response.json()
            batch = payload.get("data", []) or []
            if not batch:
                break
            for item in batch:
                if not isinstance(item, dict):
                    continue
                citing = item.get("citingPaper")
                if not isinstance(citing, dict):
                    continue
                results.append(self._normalize_paper(citing))
                if len(results) >= limit:
                    break
            offset += len(batch)

            # If the API returns fewer than requested, we are likely done.
            if len(batch) < page_size:
                break

        return results

    def _normalize_paper(self, data: Dict[str, Any]) -> SemanticScholarPaper:
        doi = normalize_doi(data.get("doi") or data.get("externalIds", {}).get("DOI"))
        authors: List[str] = []
        for author in data.get("authors", []) or []:
            if not isinstance(author, dict):
                continue
            name = author.get("name")
            if name:
                authors.append(name)
                
        open_access_pdf = data.get("openAccessPdf") or {}
        pdf_url = open_access_pdf.get("url") if isinstance(open_access_pdf, dict) else None

        return SemanticScholarPaper(
            paper_id=str(
                data.get("paperId")
                or data.get("externalIds", {}).get("CorpusId")
                or doi
                or data.get("title")
                or ""
            ),
            doi=doi,
            title=data.get("title"),
            abstract=data.get("abstract"),
            year=data.get("year"),
            venue=data.get("venue"),
            url=data.get("url"),
            pdf_url=pdf_url,
            authors=authors,
        )
