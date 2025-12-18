from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from retrieval.discovery.openalex import OpenAlexClient, OpenAlexWork
from .models import Paper


class OpenAlexService:
    """Service wrapper around :class:`OpenAlexClient` with Paper normalization."""

    def __init__(self, client: Optional[OpenAlexClient] = None) -> None:
        self.client = client or OpenAlexClient()

    def search(
        self,
        query: str,
        *,
        per_page: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        cursor: str = "*",
    ) -> Tuple[List[Paper], Optional[str]]:
        filters: Dict[str, Any] = {}
        if min_year:
            filters["from_publication_date"] = f"{min_year}-01-01"
        if max_year:
            filters["to_publication_date"] = f"{max_year}-12-31"

        works, next_cursor = self.client.search_works(
            query, per_page=per_page, cursor=cursor, filters=filters or None
        )
        papers = [self._to_paper(work) for work in works]
        return papers, next_cursor

    def get_by_doi(self, doi: str) -> Optional[Paper]:
        if not doi:
            return None
        openalex_id = doi
        if not doi.startswith("https://doi.org/"):
            openalex_id = f"https://doi.org/{doi}"
        work = self.client.get_work(openalex_id)
        return self._to_paper(work)

    def get_by_title(self, title: str, *, per_page: int = 5) -> List[Paper]:
        results, _ = self.search(title, per_page=per_page)
        return results

    def _to_paper(self, work: OpenAlexWork) -> Paper:
        return Paper(
            paper_id=work.openalex_id or work.doi or work.title or "",
            title=work.title or "",
            doi=work.doi,
            abstract=work.abstract,
            year=work.year,
            venue=work.venue,
            source="openalex",
            url=work.openalex_url,
            authors=work.authors,
        )
