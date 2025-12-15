"""Title-only MedRxiv lookups."""

from __future__ import annotations

from typing import List

import requests

from .base import BasePreprintClient, PreprintResult


class MedRxivClient(BasePreprintClient):
    provider = "medrxiv"
    BASE_URL = "https://api.biorxiv.org/details/medrxiv"

    def search(self, title: str, *, max_results: int = 5) -> List[PreprintResult]:  # type: ignore[override]
        params = {"title": title, "max_results": max_results}
        response = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return self._parse_collection(payload.get("collection", []), max_results)

    def _parse_collection(self, collection: list, max_results: int) -> List[PreprintResult]:
        results: List[PreprintResult] = []
        for item in collection[:max_results]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            doi = item.get("doi")
            link = item.get("link") or (f"https://doi.org/{doi}" if doi else "")
            pdf_url = item.get("pdf_url") or None
            published = item.get("date") or item.get("published")
            authors = item.get("authors")
            results.append(
                PreprintResult(
                    provider=self.provider,
                    title=title,
                    url=link,
                    pdf_url=pdf_url,
                    authors=authors if isinstance(authors, list) else None,
                    published=published,
                )
            )
        return results
