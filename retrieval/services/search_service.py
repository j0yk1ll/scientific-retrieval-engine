from __future__ import annotations

from typing import Iterable, List, Optional, Set

from retrieval.models import Paper

from .openalex_service import OpenAlexService
from .semanticscholar_service import SemanticScholarService


class PaperSearchService:
    """Aggregate paper search across OpenAlex and Semantic Scholar."""

    def __init__(
        self,
        *,
        openalex: Optional[OpenAlexService] = None,
        semanticscholar: Optional[SemanticScholarService] = None,
    ) -> None:
        self.openalex = openalex or OpenAlexService()
        self.semanticscholar = semanticscholar or SemanticScholarService()

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[Paper]:
        if not query:
            return []

        papers: List[Paper] = []
        seen: Set[str] = set()

        openalex_results, cursor = self.openalex.search(
            query, per_page=k, min_year=min_year, max_year=max_year
        )
        self._append_unique(openalex_results, papers, seen)

        # Repeat the query on the next OpenAlex cursor to discover more unique papers.
        if cursor:
            more_results, _ = self.openalex.search(
                query,
                per_page=k,
                min_year=min_year,
                max_year=max_year,
                cursor=cursor,
            )
            self._append_unique(more_results, papers, seen)

        semantic_results = self.semanticscholar.search(
            query, limit=k, min_year=min_year, max_year=max_year
        )
        self._append_unique(semantic_results, papers, seen)

        return papers[:k]

    def search_by_doi(self, doi: str) -> List[Paper]:
        candidates: List[Paper] = []
        seen: Set[str] = set()

        for result in (
            self.openalex.get_by_doi(doi),
            self.semanticscholar.get_by_doi(doi),
        ):
            if result:
                self._append_unique([result], candidates, seen)
        return candidates

    def search_by_title(self, title: str, *, k: int = 5) -> List[Paper]:
        results = self.search(title, k=k)
        return results

    def _append_unique(
        self, incoming: Iterable[Paper], target: List[Paper], seen: Set[str]
    ) -> None:
        for paper in incoming:
            normalized_title = (paper.title or paper.paper_id or "").lower()
            key = paper.doi or normalized_title
            if key in seen:
                continue
            seen.add(key)
            target.append(paper)
