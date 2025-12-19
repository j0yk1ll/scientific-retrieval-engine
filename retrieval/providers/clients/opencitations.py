"""Client for interacting with the OpenCitations REST API."""

from __future__ import annotations

import re
from typing import List

from retrieval.providers.clients.base import BaseHttpClient, ClientError, NotFoundError
from retrieval.core.identifiers import normalize_doi
from retrieval.core.models import Citation

_PID_PREFIXES = ("doi:", "pmid:", "omid:")
_PID_TOKEN_PATTERN = re.compile(r"(?:doi|pmid|omid):\S+", re.IGNORECASE)


def to_oc_pid(paper_id: str) -> str:
    if not paper_id:
        return ""

    cleaned = paper_id.strip()
    lowered = cleaned.lower()
    if lowered.startswith(_PID_PREFIXES):
        return cleaned

    normalized_doi = normalize_doi(cleaned)
    if normalized_doi:
        return f"doi:{normalized_doi}"

    return cleaned


def extract_preferred_pid(identifier: str) -> str:
    if not identifier:
        return ""

    cleaned = identifier.strip()
    if "=>" in cleaned:
        cleaned = cleaned.split("=>")[-1].strip()

    parts = [part.strip() for part in cleaned.split(";") if part.strip()] or [cleaned]
    tokens: List[str] = []
    for part in parts:
        tokens.extend(match.group(0) for match in _PID_TOKEN_PATTERN.finditer(part))
    if tokens:
        lowered_tokens = [token.lower() for token in tokens]
        for prefix in _PID_PREFIXES:
            for token, lowered in zip(tokens, lowered_tokens):
                if lowered.startswith(prefix):
                    if prefix == "doi:":
                        return normalize_doi(token) or token.split(":", 1)[-1].strip()
                    return token.strip()

    normalized = normalize_doi(cleaned)
    return normalized or cleaned


class OpenCitationsClient(BaseHttpClient):
    """Thin wrapper around the OpenCitations citation lookup API."""

    BASE_URL = "https://opencitations.net/index/api/v1"

    def citations(self, paper_id: str) -> List[Citation]:
        """Return citations for a given paper identifier (e.g., DOI).

        DOI-like strings are normalized before being sent to OpenCitations.
        """

        pid = to_oc_pid(paper_id)
        if not pid:
            return []

        try:
            response = self._request("GET", f"/citations/{pid}")
        except (NotFoundError, ClientError):
            return []

        payload = response.json()
        return [
            Citation(
                citing=extract_preferred_pid(item.get("citing")),
                cited=extract_preferred_pid(item.get("cited")),
                creation=item.get("creation"),
            )
            for item in payload
        ]
