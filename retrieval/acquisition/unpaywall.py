"""Unpaywall client and full-text resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import requests

from .title_match import TitleMatcher
from .preprints.base import BasePreprintClient, PreprintResult


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
class FullTextCandidate:
    """Unified representation of an acquired full-text URL."""

    source: str
    url: str
    pdf_url: Optional[str]
    metadata: Optional[dict] = None


class UnpaywallClient:
    """Minimal Unpaywall client focused on PDF resolution."""

    BASE_URL = "https://api.unpaywall.org/v2"

    def __init__(
        self,
        email: str,
        *,
        session: Optional[requests.Session] = None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        if "@" not in email:
            raise ValueError("A valid contact email is required for Unpaywall requests")

        self.email = email
        self.base_url = base_url or self.BASE_URL
        self.session = session or requests.Session()
        self.timeout = timeout

    def get_record(self, doi: str) -> UnpaywallRecord:
        """Fetch and parse an Unpaywall record for the given DOI."""

        url = f"{self.base_url}/{doi}"
        response = self.session.get(url, params={"email": self.email}, timeout=self.timeout)
        response.raise_for_status()
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
            doi=payload.get("doi", ""),
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
    preprint_clients: Sequence[BasePreprintClient],
    matcher: Optional[TitleMatcher] = None,
) -> Optional[FullTextCandidate]:
    """Resolve full text via Unpaywall, then fallback to preprints by title.

    The helper keeps network concerns inside the provided clients and uses
    :class:`TitleMatcher` to pick the most plausible preprint when Unpaywall does
    not yield a PDF URL.
    """

    matcher = matcher or TitleMatcher()

    try:
        record = unpaywall_client.get_record(doi)
    except requests.RequestException:
        record = None

    if record and record.best_pdf_url:
        return FullTextCandidate(
            source="unpaywall",
            url=record.best_pdf_url,
            pdf_url=record.best_pdf_url,
            metadata={"doi": record.doi, "title": record.title},
        )

    preprint_results: list[PreprintResult] = []
    for client in preprint_clients:
        try:
            preprint_results.extend(client.search(title))
        except requests.RequestException:
            continue

    best_match = matcher.pick_best(title, preprint_results)
    if best_match:
        return FullTextCandidate(
            source=best_match.provider,
            url=best_match.pdf_url or best_match.url,
            pdf_url=best_match.pdf_url or best_match.url,
            metadata={"title": best_match.title},
        )

    return None
