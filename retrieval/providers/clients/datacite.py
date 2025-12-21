"""DataCite client for DOI and title lookups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from retrieval.core.identifiers import normalize_doi
from retrieval.providers.clients.base import BaseHttpClient, NotFoundError


@dataclass
class DataCiteWork:
    doi: Optional[str]
    title: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    url: Optional[str]
    authors: List[str]


class DataCiteClient(BaseHttpClient):
    """Lightweight wrapper around the DataCite API."""

    BASE_URL = "https://api.datacite.org"

    def get_by_doi(self, doi: str) -> Optional[DataCiteWork]:
        normalized_doi = normalize_doi(doi)
        if not normalized_doi:
            return None

        try:
            response = self._request("GET", f"/dois/{normalized_doi}")
        except NotFoundError:
            return None

        payload = response.json().get("data") or {}
        return self._normalize_work(payload)

    def search_by_title(self, title: str, *, rows: int = 5) -> List[DataCiteWork]:
        if not title:
            return []

        results = self._search(title, rows=rows, exact=True)
        if results:
            return results

        return self._search(title, rows=rows, exact=False)

    def _search(self, title: str, *, rows: int, exact: bool) -> List[DataCiteWork]:
        query_value = self._build_query(title, exact=exact)
        params = {"query": query_value, "page[size]": rows}

        response = self._request("GET", "/dois", params=params)
        items = response.json().get("data", [])
        works: List[DataCiteWork] = []
        for item in items:
            work = self._normalize_work(item)
            if work:
                works.append(work)
        return works

    def _build_query(self, title: str, *, exact: bool) -> str:
        if exact:
            escaped = title.replace("\"", r"\"")
            return f'titles.title:"{escaped}"'
        return title

    def _normalize_work(self, data: Dict[str, Any]) -> Optional[DataCiteWork]:
        if not isinstance(data, dict):
            return None

        attributes = data.get("attributes", {}) if isinstance(data.get("attributes"), dict) else {}

        doi = normalize_doi(attributes.get("doi") or data.get("id"))
        title = self._extract_title(attributes.get("titles"))
        authors = self._extract_authors(attributes.get("creators") or [])
        year = self._extract_year(attributes.get("publicationYear"))
        venue = self._extract_venue(attributes)
        url = attributes.get("url")

        if not title and not doi:
            return None

        return DataCiteWork(
            doi=doi,
            title=title,
            year=year,
            venue=venue,
            url=url,
            authors=authors,
        )

    def _extract_title(self, titles: Any) -> Optional[str]:
        if isinstance(titles, list) and titles:
            first = titles[0]
            if isinstance(first, dict) and first.get("title"):
                return str(first.get("title"))
            if isinstance(first, str):
                return first
        return None

    def _extract_authors(self, creators: List[Dict[str, Any]]) -> List[str]:
        extracted: List[str] = []
        for creator in creators:
            if not isinstance(creator, dict):
                continue
            name = creator.get("name") or creator.get("creatorName")
            if name:
                extracted.append(str(name))
                continue
            given = creator.get("givenName")
            family = creator.get("familyName")
            if given and family:
                extracted.append(f"{given} {family}")
            elif given or family:
                extracted.append(str(given or family))
        return extracted

    def _extract_year(self, year_value: Any) -> Optional[int]:
        if isinstance(year_value, int):
            return year_value
        if isinstance(year_value, str) and year_value.isdigit():
            return int(year_value)
        return None

    def _extract_venue(self, attributes: Dict[str, Any]) -> Optional[str]:
        venue = attributes.get("publisher")
        if venue:
            return str(venue)

        container = attributes.get("container")
        if isinstance(container, dict):
            title = container.get("title")
            if title:
                return str(title)
        return None
