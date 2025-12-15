"""Title-only ChemRxiv lookups."""

from __future__ import annotations

from typing import List

import requests

from .base import BasePreprintClient, PreprintResult


class ChemRxivClient(BasePreprintClient):
    provider = "chemrxiv"
    BASE_URL = "https://chemrxiv.org/engage/chemrxiv/public-api/v1/items"

    def search(self, title: str, *, max_results: int = 5) -> List[PreprintResult]:  # type: ignore[override]
        params = {"search": title, "limit": max_results}
        response = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return self._parse_items(payload.get("items", []), max_results)

    def _parse_items(self, items: list, max_results: int) -> List[PreprintResult]:
        results: List[PreprintResult] = []
        for item in items[:max_results]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            item_id = item.get("id") or item.get("doi")
            link = item.get("url") or (f"https://doi.org/{item_id}" if item_id else "")
            pdf_url = item.get("pdf_url") or item.get("download")
            results.append(
                PreprintResult(
                    provider=self.provider,
                    title=title,
                    url=link,
                    pdf_url=pdf_url,
                    authors=item.get("authors"),
                    published=item.get("published"),
                )
            )
        return results
