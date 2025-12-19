"""Client for querying OpenAlex for metadata discovery."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from retrieval.clients.base import (
    BaseHttpClient,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    RequestRejectedError,
    UnauthorizedError,
    UpstreamError,
)
from retrieval.identifiers import normalize_doi

logger = logging.getLogger(__name__)


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


class OpenAlexClient(BaseHttpClient):
    """Lightweight wrapper around the OpenAlex Works API."""

    BASE_URL = "https://api.openalex.org"

    def get_work(self, openalex_work_id: str) -> Optional[OpenAlexWork]:
        """Fetch a single work by its OpenAlex identifier."""

        return self._get_work_by_path(f"/works/{openalex_work_id}", identifier=openalex_work_id)

    def get_work_by_external_id(self, external_id: str) -> Optional[OpenAlexWork]:
        """Fetch a work by external identifier (e.g., DOI URL)."""

        encoded = quote(external_id, safe="")
        return self._get_work_by_path(f"/works/{encoded}", identifier=external_id)

    def get_work_by_doi_filter(self, doi_url: str) -> Optional[OpenAlexWork]:
        """Fetch a work using the DOI filter fallback."""

        params: Dict[str, Any] = {"filter": f"doi:{doi_url}"}
        try:
            response = self._request("GET", "/works", params=params)
        except NotFoundError:
            self._log_failed_request("doi_filter", doi_url, status=404, detail="Not found")
            return None
        except (RequestRejectedError, UnauthorizedError, ForbiddenError) as exc:
            self._log_failed_request("doi_filter", doi_url, status=exc.status, detail=exc.body_excerpt)
            return None
        except RateLimitedError as exc:
            self._log_failed_request("doi_filter", doi_url, status=429, detail=str(exc))
            return None
        except UpstreamError as exc:
            self._log_failed_request("doi_filter", doi_url, status=None, detail=str(exc))
            return None

        payload = response.json()
        results = payload.get("results") or []
        if not results:
            return None
        return self._normalize_work(results[0])

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

    def _get_work_by_path(self, path: str, *, identifier: str) -> Optional[OpenAlexWork]:
        try:
            response = self._request("GET", path)
        except NotFoundError:
            self._log_failed_request("work_lookup", identifier, status=404, detail="Not found")
            return None
        except (RequestRejectedError, UnauthorizedError, ForbiddenError) as exc:
            self._log_failed_request("work_lookup", identifier, status=exc.status, detail=exc.body_excerpt)
            return None
        except RateLimitedError as exc:
            self._log_failed_request("work_lookup", identifier, status=429, detail=str(exc))
            return None
        except UpstreamError as exc:
            self._log_failed_request("work_lookup", identifier, status=None, detail=str(exc))
            return None

        payload = response.json()
        return self._normalize_work(payload)

    def _log_failed_request(
        self,
        operation: str,
        identifier: str,
        *,
        status: Optional[int],
        detail: Optional[str],
    ) -> None:
        detail_message = f" detail={detail}" if detail else ""
        logger.debug(
            "OpenAlex %s failed for identifier=%s status=%s%s",
            operation,
            identifier,
            status,
            detail_message,
        )

    def _normalize_work(self, data: Dict[str, Any]) -> OpenAlexWork:
        openalex_id = self._normalize_openalex_id(data.get("id"))
        doi = normalize_doi(data.get("doi"))
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

    def _normalize_venue(self, host_venue: Any) -> Optional[str]:
        if isinstance(host_venue, dict):
            return host_venue.get("display_name") or host_venue.get("publisher")
        return None
