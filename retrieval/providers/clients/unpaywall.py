"""Unpaywall client and full-text resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from retrieval.core.identifiers import normalize_doi
from retrieval.providers.clients.base import BaseHttpClient, ClientError, NotFoundError


@dataclass
class OpenAccessLocation:
    """Representation of an Unpaywall location candidate."""

    url: str
    url_for_pdf: Optional[str]
    version: Optional[str]
    license: Optional[str]
    host_type: Optional[str]
    is_best: bool = False

    @property
    def pdf_url(self) -> Optional[str]:
        """Return the most likely PDF URL for the location."""

        return self.url_for_pdf or self.url


@dataclass
class UnpaywallRecord:
    """Parsed Unpaywall response payload."""

    doi: str
    title: Optional[str]
    best_oa_location: Optional[OpenAccessLocation]
    oa_locations: List[OpenAccessLocation]

    @property
    def best_pdf_url(self) -> Optional[str]:
        if self.best_oa_location:
            return self.best_oa_location.pdf_url
        if self.oa_locations:
            return self.oa_locations[0].pdf_url
        return None


@dataclass
class UnpaywallFullTextCandidate:
    """Unified representation of an acquired full-text URL."""

    source: str
    url: str
    pdf_url: Optional[str]
    metadata: Optional[dict] = None


class UnpaywallClient(BaseHttpClient):
    """Minimal Unpaywall client focused on PDF resolution."""

    BASE_URL = "https://api.unpaywall.org/v2"

    def __init__(
        self,
        email: str,
        *,
        session=None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        if "@" not in email:
            raise ValueError("A valid contact email is required for Unpaywall requests")

        self.email = email
        super().__init__(session=session, base_url=base_url, timeout=timeout)

    def get_record(self, doi: str) -> Optional[UnpaywallRecord]:
        """Fetch and parse an Unpaywall record for the given DOI."""

        normalized_doi = normalize_doi(doi)
        if not normalized_doi:
            raise ValueError("DOI is required for Unpaywall requests")

        try:
            response = self._request("GET", f"/{normalized_doi}", params={"email": self.email})
        except NotFoundError:
            return None
        payload = response.json()
        return self._parse_record(payload)

    def _parse_record(self, payload: dict) -> UnpaywallRecord:
        locations = [
            self._parse_location(location)
            for location in payload.get("oa_locations", [])
            if isinstance(location, dict)
        ]

        best_location_data = payload.get("best_oa_location")
        best_location = self._parse_location(best_location_data) if isinstance(best_location_data, dict) else None

        if best_location and best_location not in locations:
            locations.insert(0, best_location)

        return UnpaywallRecord(
            doi=normalize_doi(payload.get("doi")) or "",
            title=payload.get("title"),
            best_oa_location=best_location,
            oa_locations=locations,
        )

    def _parse_location(self, data: dict) -> OpenAccessLocation:
        return OpenAccessLocation(
            url=data.get("url") or "",
            url_for_pdf=data.get("url_for_pdf"),
            version=data.get("version"),
            license=data.get("license"),
            host_type=data.get("host_type"),
            is_best=bool(data.get("is_best")),
        )


def resolve_full_text(
    *,
    doi: str,
    title: str,
    unpaywall_client: UnpaywallClient,
) -> Optional[UnpaywallFullTextCandidate]:
    """Resolve full text via Unpaywall without scraping or alternate fallbacks.

    The helper keeps network concerns inside the provided client and returns the
    best open-access PDF URL when Unpaywall supplies one. The ``title`` is used
    only for metadata symmetry with other call sites and is not resolved against
    external sources.
    """

    try:
        record = unpaywall_client.get_record(doi)
    except ClientError:
        record = None

    if record and record.best_pdf_url:
        return UnpaywallFullTextCandidate(
            source="unpaywall",
            url=record.best_pdf_url,
            pdf_url=record.best_pdf_url,
            metadata={"doi": record.doi, "title": record.title},
        )

    return None
