from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

from retrieval.identifiers import normalize_doi, normalize_title
from retrieval.models import Paper
from retrieval.services.paper_merge_service import PaperMergeService

from .crossref_service import CrossrefService
from .doi_resolver_service import DoiResolverService
from .openalex_service import OpenAlexService
from .semanticscholar_service import SemanticScholarService


logger = logging.getLogger(__name__)


class PaperSearchService:
    """Aggregate paper search across OpenAlex and Semantic Scholar.

    The service resolves papers only by DOI or title and intentionally avoids
    URL-based lookups or preprint-specific logic.
    """

    def __init__(
        self,
        *,
        openalex: Optional[OpenAlexService] = None,
        semanticscholar: Optional[SemanticScholarService] = None,
        crossref: Optional[CrossrefService] = None,
        doi_resolver: Optional[DoiResolverService] = None,
        merge_service: Optional[PaperMergeService] = None,
    ) -> None:
        self.openalex = openalex or OpenAlexService()
        self.semanticscholar = semanticscholar or SemanticScholarService()
        self.crossref = crossref or CrossrefService()
        self.doi_resolver = doi_resolver or DoiResolverService(crossref=self.crossref)
        self.merge_service = merge_service or PaperMergeService()

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> List[Paper]:
        merged, _ = self.search_with_raw(
            query,
            k=k,
            min_year=min_year,
            max_year=max_year,
            include_raw=False,
            openalex_extra_pages=0,
        )
        return merged

    def search_with_raw(
        self,
        query: str,
        *,
        k: int = 5,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
        include_raw: bool = True,
        use_openalex_cursor: bool = False,
        openalex_extra_pages: int = 0,
    ) -> Tuple[List[Paper], List[Paper]]:
        if not query:
            return [], []

        grouped: Dict[str, List[Paper]] = {}
        order: List[str] = []

        openalex_results, cursor = self.openalex.search(
            query, per_page=k, min_year=min_year, max_year=max_year
        )
        self._append_to_groups(openalex_results, grouped, order)

        pages_to_fetch = openalex_extra_pages
        if use_openalex_cursor and pages_to_fetch == 0:
            pages_to_fetch = 1

        while cursor and pages_to_fetch > 0:
            more_results, cursor = self.openalex.search(
                query,
                per_page=k,
                min_year=min_year,
                max_year=max_year,
                cursor=cursor,
            )
            self._append_to_groups(more_results, grouped, order)
            pages_to_fetch -= 1

        semantic_results = self.semanticscholar.search(
            query, limit=k, min_year=min_year, max_year=max_year
        )
        self._append_to_groups(semantic_results, grouped, order)

        merged_results = [
            self.merge_service.merge(grouped[key]) for key in order
        ][:k]
        raw_results = [paper for key in order for paper in grouped[key]] if include_raw else []

        return merged_results, raw_results

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
            key = self._make_group_key(paper)
            if key in seen:
                continue
            seen.add(key)
            target.append(paper)

    def _append_to_groups(
        self, incoming: Iterable[Paper], grouped: Dict[str, List[Paper]], order: List[str]
    ) -> None:
        for paper in incoming:
            key = self._make_group_key(paper)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(paper)

    def _make_group_key(self, paper: Paper) -> str:
        normalized_doi = normalize_doi(paper.doi)
        if normalized_doi:
            return f"doi:{normalized_doi}"

        normalized_title = normalize_title(paper.title or paper.paper_id or "")
        components = [normalized_title]
        if paper.year:
            components.append(str(paper.year))
        if paper.authors:
            components.append(normalize_title(paper.authors[0]))
        return "|".join(components)
