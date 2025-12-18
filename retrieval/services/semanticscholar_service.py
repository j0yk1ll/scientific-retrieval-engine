from __future__ import annotations

from typing import List, Optional

from retrieval.clients.semanticscholar import (
    DEFAULT_FIELDS,
    SemanticScholarClient,
    SemanticScholarPaper,
)
from retrieval.identifiers import normalize_doi
from retrieval.models import Paper


class SemanticScholarService:
    """Service wrapper around :class:`SemanticScholarClient` with Paper normalization."""

    def __init__(self, client: Optional[SemanticScholarClient] = None) -> None:
        self.client = client or SemanticScholarClient()

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[Paper]:
        results = self.client.search_papers(
            query,
            limit=limit,
            min_year=min_year,
            max_year=max_year,
            fields=DEFAULT_FIELDS,
        )
        return [self._to_paper(record) for record in results]

    def get_by_doi(self, doi: str) -> Optional[Paper]:
        record = self.client.get_by_doi(doi, fields=DEFAULT_FIELDS)
        if record is None:
            return None
        return self._to_paper(record)

    def get_by_title(self, title: str, *, limit: int = 5) -> List[Paper]:
        return self.search(title, limit=limit)

    def _to_paper(self, record: SemanticScholarPaper) -> Paper:
        return Paper(
            paper_id=record.paper_id or record.doi or record.title or "",
            title=record.title or "",
            doi=normalize_doi(record.doi),
            abstract=record.abstract,
            year=record.year,
            venue=record.venue,
            source="semanticscholar",
            url=record.url,
            authors=record.authors,
        )
