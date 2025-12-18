"""Client for querying OpenAlex for metadata discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass
class OpenAlexWork:
    """Normalized representation of an OpenAlex work."""

    openalex_id: str
    openalex_url: str
    doi: Optional[str]
    title: Optional[str]
    year: Optional[int]
    venue: Optional[str]
    abstract: Optional[str]
    authors: List[str]
    referenced_works: List[str]


class OpenAlexClient:
    """Lightweight wrapper around the OpenAlex Works API."""

    BASE_URL = "https://api.openalex.org"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        base_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_work(self, openalex_work_id: str) -> OpenAlexWork:
        """Fetch a single work by its OpenAlex identifier."""

        response = self._request("GET", f"/works/{openalex_work_id}")
        payload = response.json()
        return self._normalize_work(payload)

    def search_works(
        self,
        query: str,
        *,
        per_page: int = 5,
        cursor: str = "*",
        filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[OpenAlexWork], Optional[str]]:
        """Search works via the OpenAlex API."""

        params: Dict[str, Any] = {"search": query, "per-page": per_page, "cursor": cursor}
        if filters:
            params["filter"] = ",".join(f"{key}:{value}" for key, value in filters.items())

        response = self._request("GET", "/works", params=params)
        payload = response.json()
        works = [self._normalize_work(item) for item in payload.get("results", [])]
        next_cursor = payload.get("meta", {}).get("next_cursor")
        return works, next_cursor

    def _normalize_work(self, data: Dict[str, Any]) -> OpenAlexWork:
        openalex_id = self._normalize_openalex_id(data.get("id"))
        doi = self._normalize_doi(data.get("doi"))
        title = data.get("display_name") or data.get("title")
        year = data.get("publication_year")
        venue = self._normalize_venue(data.get("host_venue"))
        abstract = self._extract_abstract(data)
        authors = self._extract_authors(data.get("authorships", []))
        referenced_works = [self._normalize_openalex_id(item) for item in data.get("referenced_works", [])]

        return OpenAlexWork(
            openalex_id=openalex_id,
            openalex_url=f"https://openalex.org/{openalex_id}" if openalex_id else "",
            doi=doi,
            title=title,
            year=year,
            venue=venue,
            abstract=abstract,
            authors=authors,
            referenced_works=referenced_works,
        )

    def _extract_authors(self, authorships: Iterable[Dict[str, Any]]) -> List[str]:
        authors: List[str] = []
        for authorship in authorships:
            author = authorship.get("author") or {}
            name = author.get("display_name") or author.get("name")
            if name:
                authors.append(name)
        return authors

    def _extract_abstract(self, data: Dict[str, Any]) -> Optional[str]:
        if "abstract_inverted_index" in data and isinstance(data["abstract_inverted_index"], dict):
            return self._reconstruct_abstract(data["abstract_inverted_index"])
        return data.get("abstract")

    def _reconstruct_abstract(self, inverted_index: Dict[str, List[int]]) -> Optional[str]:
        positions: List[tuple[int, str]] = []
        for word, indices in inverted_index.items():
            for position in indices:
                positions.append((position, word))

        if not positions:
            return None

        positions.sort(key=lambda item: item[0])
        max_position = positions[-1][0]
        words: List[str] = [""] * (max_position + 1)
        for position, word in positions:
            words[position] = word

        return " ".join(words).strip()

    def _normalize_openalex_id(self, raw_id: Optional[str]) -> str:
        if not raw_id:
            return ""
        return raw_id.rsplit("/", 1)[-1]

    def _normalize_doi(self, raw_doi: Optional[str]) -> Optional[str]:
        if not raw_doi:
            return None
        prefix = "doi.org/"
        if prefix in raw_doi:
            return raw_doi.split(prefix, 1)[1]
        return raw_doi.replace("DOI:", "").strip()

    def _normalize_venue(self, host_venue: Any) -> Optional[str]:
        if isinstance(host_venue, dict):
            return host_venue.get("display_name") or host_venue.get("publisher")
        return None
