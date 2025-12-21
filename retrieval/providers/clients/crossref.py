"""Crossref client for DOI resolution and metadata discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from retrieval.core.identifiers import normalize_doi
from retrieval.providers.clients.base import BaseHttpClient, NotFoundError


@dataclass
class CrossrefWork:
    doi: Optional[str]
    title: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    url: Optional[str]
    authors: List[str]


class CrossrefClient(BaseHttpClient):
    """Lightweight wrapper around the Crossref works API."""

    BASE_URL = "https://api.crossref.org"

    def works_by_doi(self, doi: str) -> Optional[CrossrefWork]:
        normalized_doi = normalize_doi(doi)
        if not normalized_doi:
            return None

        try:
            response = self._request("GET", f"/works/{normalized_doi}")
        except NotFoundError:
            return None

        payload = response.json().get("message", {})
        return self._normalize_work(payload)

    def search_by_title(
        self,
        title: str,
        *,
        rows: int = 5,
        from_year: Optional[int] = None,
        until_year: Optional[int] = None,
    ) -> List[CrossrefWork]:
        if not title:
            return []

        params: Dict[str, Any] = {
            "query.bibliographic": title,
            "query.title": title,
            "rows": rows,
            "select": "DOI,title,issued,author,container-title,URL,score",
            "sort": "score",
            "order": "desc",
        }

        filters: List[str] = []
        if from_year is not None:
            filters.append(f"from-pub-date:{from_year}-01-01")
        if until_year is not None:
            filters.append(f"until-pub-date:{until_year}-12-31")
        if filters:
            params["filter"] = ",".join(filters)

        response = self._request("GET", "/works", params=params)
        items = response.json().get("message", {}).get("items", [])
        works: List[CrossrefWork] = []
        for item in items:
            work = self._normalize_work(item)
            if work:
                works.append(work)
        return works

    def _normalize_work(self, data: Dict[str, Any]) -> Optional[CrossrefWork]:
        if not isinstance(data, dict):
            return None

        doi = normalize_doi(data.get("DOI"))
        title_parts = data.get("title") or []
        title = title_parts[0] if isinstance(title_parts, list) and title_parts else None
        authors = self._extract_authors(data.get("author") or [])
        year = self._extract_year(data)
        venue = self._extract_venue(data)
        url = data.get("URL")

        if not title and not doi:
            return None

        return CrossrefWork(
            doi=doi,
            title=title,
            year=year,
            venue=venue,
            url=url,
            authors=authors,
        )

    def _extract_year(self, data: Dict[str, Any]) -> Optional[int]:
        for key in ("issued", "published-print", "published-online"):
            component = data.get(key, {})
            if not isinstance(component, dict):
                continue
            parts = component.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                year = parts[0][0]
                if isinstance(year, int):
                    return year
        return None

    def _extract_authors(self, authors: List[Dict[str, Any]]) -> List[str]:
        extracted: List[str] = []
        for author in authors:
            if not isinstance(author, dict):
                continue
            family = author.get("family")
            given = author.get("given")
            if family and given:
                extracted.append(f"{given} {family}")
            elif family or given:
                extracted.append(str(family or given))
        return extracted

    def _extract_venue(self, data: Dict[str, Any]) -> Optional[str]:
        container_title = data.get("container-title")
        if isinstance(container_title, list) and container_title:
            return container_title[0]
        return None
