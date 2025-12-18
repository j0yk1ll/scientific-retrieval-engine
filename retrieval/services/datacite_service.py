from __future__ import annotations

from typing import List, Optional

from retrieval.clients.datacite import DataCiteClient, DataCiteWork
from retrieval.identifiers import normalize_doi
from retrieval.models import Paper


class DataCiteService:
    """Service wrapper around :class:`DataCiteClient` with Paper normalization."""

    def __init__(self, client: Optional[DataCiteClient] = None) -> None:
        self.client = client or DataCiteClient()

    def search_by_title(self, title: str, *, rows: int = 5) -> List[Paper]:
        works = self.client.search_by_title(title, rows=rows)
        return [self._to_paper(work) for work in works]

    def get_by_doi(self, doi: str) -> Optional[Paper]:
        normalized_doi = normalize_doi(doi)
        if not normalized_doi:
            return None

        work = self.client.get_by_doi(normalized_doi)
        if work is None:
            return None
        return self._to_paper(work)

    def _to_paper(self, work: DataCiteWork) -> Paper:
        return Paper(
            paper_id=work.doi or work.title or "",
            title=work.title or "",
            doi=normalize_doi(work.doi),
            abstract=None,
            year=work.year,
            venue=work.venue,
            source="datacite",
            url=work.url,
            authors=work.authors,
        )
