from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Set

from retrieval.identifiers import normalize_doi, normalize_title
from retrieval.models import Paper

from .crossref_service import CrossrefService
from .doi_resolver_service import DoiResolverService
from .openalex_service import OpenAlexService
from .semanticscholar_service import SemanticScholarService


logger = logging.getLogger(__name__)


class PaperSearchService:
    """Aggregate paper search across OpenAlex and Semantic Scholar."""

    def __init__(
        self,
        *,
        openalex: Optional[OpenAlexService] = None,
        semanticscholar: Optional[SemanticScholarService] = None,
        crossref: Optional[CrossrefService] = None,
        doi_resolver: Optional[DoiResolverService] = None,
    ) -> None:
        self.openalex = openalex or OpenAlexService()
        self.semanticscholar = semanticscholar or SemanticScholarService()
        self.crossref = crossref or CrossrefService()
        self.doi_resolver = doi_resolver or DoiResolverService(crossref=self.crossref)

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
            self.crossref.get_by_doi(doi),
            self.openalex.get_by_doi(doi),
            self.semanticscholar.get_by_doi(doi),
        ):
            if result:
                self._append_unique([result], candidates, seen)
        return candidates

    def search_by_title(self, title: str, *, k: int = 5) -> List[Paper]:
        initial_results = self.search(title, k=k)

        resolved_results, seen = self._resolve_missing_dois(title, initial_results)

        if len(resolved_results) < k:
            crossref_candidates = self.crossref.search_by_title(title, rows=k)
            self._append_unique(crossref_candidates, resolved_results, seen)

        return resolved_results[:k]

    def _resolve_missing_dois(
        self, query_title: str, papers: List[Paper]
    ) -> tuple[List[Paper], Set[str]]:
        resolved: List[Paper] = []
        seen: Set[str] = set()

        for paper in papers:
            if paper.doi:
                self._append_unique([paper], resolved, seen)
                continue

            resolved_doi = self.doi_resolver.resolve_doi_from_title(
                paper.title or query_title, expected_authors=paper.authors or None
            )
            if resolved_doi:
                canonical = self._fetch_canonical_by_doi(resolved_doi)
                if canonical:
                    logger.info(
                        "Upgraded paper metadata via DOI resolution",
                        extra={
                            "title": paper.title or query_title,
                            "doi": resolved_doi,
                            "source": canonical.source,
                        },
                    )
                    self._append_unique([canonical], resolved, seen)
                    continue

            self._append_unique([paper], resolved, seen)

        return resolved, seen

    def _fetch_canonical_by_doi(self, doi: str) -> Optional[Paper]:
        for resolver in (
            self.crossref.get_by_doi,
            self.openalex.get_by_doi,
            self.semanticscholar.get_by_doi,
        ):
            paper = resolver(doi)
            if paper:
                return paper
        return None

    def _append_unique(
        self, incoming: Iterable[Paper], target: List[Paper], seen: Set[str]
    ) -> None:
        for paper in incoming:
            normalized_doi = normalize_doi(paper.doi)
            if normalized_doi:
                key = f"doi:{normalized_doi}"
            else:
                normalized_title = normalize_title(paper.title or paper.paper_id or "")
                components = [normalized_title]
                if paper.year:
                    components.append(str(paper.year))
                if paper.authors:
                    components.append(normalize_title(paper.authors[0]))
                key = "|".join(components)
            if key in seen:
                continue
            seen.add(key)
            target.append(paper)
