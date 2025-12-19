from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from retrieval.providers.adapters import (
    crossref_work_to_paper,
    datacite_work_to_paper,
    openalex_work_to_paper,
    semanticscholar_paper_to_paper,
)
from retrieval.providers.clients.crossref import CrossrefClient
from retrieval.providers.clients.datacite import DataCiteClient
from retrieval.providers.clients.openalex import OpenAlexClient
from retrieval.providers.clients.semanticscholar import DEFAULT_FIELDS, SemanticScholarClient
from retrieval.core.identifiers import normalize_doi, normalize_title
from retrieval.core.models import Paper
from retrieval.services.paper_merge_service import PaperMergeService
from .doi_resolver_service import DoiResolverService


logger = logging.getLogger(__name__)


class PaperSearchService:
    """Aggregate paper search across OpenAlex and Semantic Scholar.

    The service resolves papers only by DOI or title and intentionally avoids
    URL-based lookups. Missing DOIs are upgraded through Crossref/DataCite title
    resolution when possible so merged results favor canonical identifiers.

    Soft grouping is enabled by default to merge slight title variants (e.g.,
    punctuation or short token swaps) that represent the same work. Grouping is
    intentionally conservative to avoid collapsing distinct short titles: the
    Jaccard threshold is never lower than 0.82 and only the first six tokens are
    compared when looking for a match.
    """

    def __init__(
        self,
        *,
        openalex: Optional[OpenAlexClient] = None,
        semanticscholar: Optional[SemanticScholarClient] = None,
        crossref: Optional[CrossrefClient] = None,
        datacite: Optional[DataCiteClient] = None,
        doi_resolver: Optional[DoiResolverService] = None,
        merge_service: Optional[PaperMergeService] = None,
        enable_soft_grouping: bool = True,
        soft_grouping_threshold: float = 0.82,
        soft_grouping_prefix_tokens: int = 6,
    ) -> None:
        self.openalex = openalex or OpenAlexClient()
        self.semanticscholar = semanticscholar or SemanticScholarClient()
        self.crossref = crossref or CrossrefClient()
        self.datacite = datacite or DataCiteClient()
        self.doi_resolver = doi_resolver or DoiResolverService(
            crossref=self.crossref, datacite=self.datacite
        )
        self.merge_service = merge_service or PaperMergeService()
        self.enable_soft_grouping = enable_soft_grouping
        self.soft_grouping_threshold = max(soft_grouping_threshold, 0.82)
        self.soft_grouping_prefix_tokens = soft_grouping_prefix_tokens

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

        openalex_works, cursor = self._search_openalex(
            query, per_page=k, min_year=min_year, max_year=max_year
        )
        openalex_results = [openalex_work_to_paper(work) for work in openalex_works]
        self._append_to_groups(openalex_results, grouped, order)

        pages_to_fetch = openalex_extra_pages
        if use_openalex_cursor and pages_to_fetch == 0:
            pages_to_fetch = 1

        while cursor and pages_to_fetch > 0:
            more_works, cursor = self._search_openalex(
                query,
                per_page=k,
                min_year=min_year,
                max_year=max_year,
                cursor=cursor,
            )
            more_results = [openalex_work_to_paper(work) for work in more_works]
            self._append_to_groups(more_results, grouped, order)
            pages_to_fetch -= 1

        semantic_records = self.semanticscholar.search_papers(
            query,
            limit=k,
            min_year=min_year,
            max_year=max_year,
            fields=DEFAULT_FIELDS,
        )
        semantic_results = [semanticscholar_paper_to_paper(record) for record in semantic_records]
        self._append_to_groups(semantic_results, grouped, order)

        merged_results = [
            self.merge_service.merge(grouped[key]) for key in order
        ][:k]
        raw_results = [paper for key in order for paper in grouped[key]] if include_raw else []

        return merged_results, raw_results

    def search_by_doi(self, doi: str) -> List[Paper]:
        candidates: List[Paper] = []
        seen: Set[str] = set()

        crossref_work = self.crossref.works_by_doi(doi)
        if crossref_work:
            self._append_unique([crossref_work_to_paper(crossref_work)], candidates, seen)

        datacite_work = self.datacite.get_by_doi(doi)
        if datacite_work:
            self._append_unique([datacite_work_to_paper(datacite_work)], candidates, seen)

        openalex_work = self.openalex.get_work_by_doi(doi)
        if openalex_work:
            self._append_unique([openalex_work_to_paper(openalex_work)], candidates, seen)

        semantic_record = self.semanticscholar.get_by_doi(doi, fields=DEFAULT_FIELDS)
        if semantic_record:
            self._append_unique(
                [semanticscholar_paper_to_paper(semantic_record)], candidates, seen
            )
        return candidates

    def search_by_title(self, title: str, *, k: int = 5) -> List[Paper]:
        initial_results = self.search(title, k=k)

        resolved_results, seen = self._resolve_missing_dois(title, initial_results)

        if len(resolved_results) < k:
            crossref_candidates = [
                crossref_work_to_paper(work)
                for work in self.crossref.search_by_title(title, rows=k)
            ]
            self._append_unique(crossref_candidates, resolved_results, seen)

        if len(resolved_results) < k:
            datacite_candidates = [
                datacite_work_to_paper(work)
                for work in self.datacite.search_by_title(title, rows=k)
            ]
            self._append_unique(datacite_candidates, resolved_results, seen)

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
        crossref_work = self.crossref.works_by_doi(doi)
        if crossref_work:
            return crossref_work_to_paper(crossref_work)

        datacite_work = self.datacite.get_by_doi(doi)
        if datacite_work:
            return datacite_work_to_paper(datacite_work)

        openalex_work = self.openalex.get_work_by_doi(doi)
        if openalex_work:
            return openalex_work_to_paper(openalex_work)

        semantic_record = self.semanticscholar.get_by_doi(doi, fields=DEFAULT_FIELDS)
        if semantic_record:
            return semanticscholar_paper_to_paper(semantic_record)
        return None

    def _search_openalex(
        self,
        query: str,
        *,
        per_page: int,
        min_year: Optional[int],
        max_year: Optional[int],
        cursor: str = "*",
    ) -> Tuple[List, Optional[str]]:
        filters: Dict[str, Any] = {}
        if min_year:
            filters["from_publication_date"] = f"{min_year}-01-01"
        if max_year:
            filters["to_publication_date"] = f"{max_year}-12-31"

        return self.openalex.search_works(
            query, per_page=per_page, cursor=cursor, filters=filters or None
        )

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
            if self.enable_soft_grouping:
                soft_key = self._find_soft_group_match(paper, grouped)
                if soft_key:
                    key = soft_key
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(paper)

    def _make_group_key(self, paper: Paper) -> str:
        normalized_doi = normalize_doi(paper.doi)
        if normalized_doi:
            return f"doi:{normalized_doi}"

        paper_id_doi = self._paper_id_as_doi(paper.paper_id)
        if paper_id_doi:
            return f"doi:{paper_id_doi}"

        normalized_title = normalize_title(paper.title or paper.paper_id or "")
        components = [normalized_title]

        tokens = self._tokenize_title(normalized_title)
        ambiguous_title = len(tokens) <= 3 or len(normalized_title) <= 25

        if ambiguous_title and paper.year:
            components.append(str(paper.year))
        if ambiguous_title and paper.authors:
            components.append(normalize_title(paper.authors[0]))
        return "|".join(components)

    def _paper_id_as_doi(self, paper_id: Optional[str]) -> Optional[str]:
        normalized = normalize_doi(paper_id)
        if not normalized:
            return None

        if normalized.startswith("10.") and "/" in normalized:
            return normalized

        return None

    def _find_soft_group_match(
        self, paper: Paper, grouped: Dict[str, List[Paper]]
    ) -> Optional[str]:
        normalized_doi = normalize_doi(paper.doi)
        if normalized_doi or not paper.title:
            return None

        normalized_title = normalize_title(paper.title)
        candidate_tokens = self._tokenize_title(normalized_title)
        if not candidate_tokens:
            return None
        if len(candidate_tokens) <= 3 or len(normalized_title) <= 25:
            return None

        prefix = self._title_prefix(candidate_tokens)

        best_key: Optional[str] = None
        best_score = 0.0

        for key, grouped_papers in grouped.items():
            if key.startswith("doi:"):
                continue

            representative = grouped_papers[0]
            if not representative.title:
                continue

            representative_tokens = self._tokenize_title(
                normalize_title(representative.title)
            )
            if not representative_tokens:
                continue

            if self._title_prefix(representative_tokens) != prefix:
                continue

            similarity = self._jaccard_similarity(candidate_tokens, representative_tokens)
            if similarity >= self.soft_grouping_threshold and similarity > best_score:
                best_key = key
                best_score = similarity

        return best_key

    def _tokenize_title(self, normalized_title: str) -> List[str]:
        if not normalized_title:
            return []
        return re.findall(r"[a-z0-9]+", normalized_title)

    def _title_prefix(self, tokens: List[str]) -> str:
        return " ".join(tokens[: self.soft_grouping_prefix_tokens])

    def _jaccard_similarity(self, left: List[str], right: List[str]) -> float:
        if not left or not right:
            return 0.0

        left_set = set(left)
        right_set = set(right)
        intersection = len(left_set & right_set)
        union = len(left_set | right_set)
        if union == 0:
            return 0.0
        return intersection / union
