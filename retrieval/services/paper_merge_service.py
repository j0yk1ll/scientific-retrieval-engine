from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from retrieval.core.identifiers import normalize_doi
from retrieval.core.models import Paper


DEFAULT_SOURCE_PRIORITY = ("crossref", "datacite", "openalex", "semanticscholar")

PrioritySpec = Sequence[str | Sequence[str]]
PriorityGroups = Tuple[Tuple[str, ...], ...]


class PaperMergeService:
    """Merge multiple records for the same paper into a single enriched record."""

    def __init__(self, *, source_priority: PrioritySpec | None = None) -> None:
        self.priority_groups: PriorityGroups = self._normalize_priority_spec(
            source_priority or DEFAULT_SOURCE_PRIORITY
        )
        self.source_priority: Dict[str, int] = {}
        for idx, group in enumerate(self.priority_groups):
            for source in group:
                self.source_priority[source] = idx

    def merge(self, papers: List[Paper]) -> Paper:
        if not papers:
            raise ValueError("Cannot merge an empty collection of papers")

        primary_index = self._primary_source_index(papers)
        doi_value = self._select_field(
            papers,
            "doi",
            self._is_non_empty,
            priority_order=self.priority_groups,
            transform=normalize_doi,
        )

        paper_id_value = self._select_field(
            papers,
            "paper_id",
            self._is_non_empty,
            preferred_value=doi_value,
            priority_order=self.priority_groups,
        )

        title_value = self._select_field(
            papers,
            "title",
            self._is_non_empty,
            priority_order=self.priority_groups,
        )
        abstract_value = self._select_field(
            papers,
            "abstract",
            self._is_non_empty,
            priority_order=self._normalize_priority_spec(
                (("openalex", "semanticscholar"), *self.priority_groups)
            ),
            tie_breaker=self._prefer_longer_text,
        )
        year_value = self._select_field(
            papers,
            "year",
            self._is_not_none,
            priority_order=self.priority_groups,
        )
        venue_value = self._select_field(
            papers,
            "venue",
            self._is_non_empty,
            priority_order=self.priority_groups,
        )
        url_value = self._select_field(
            papers,
            "url",
            self._is_non_empty,
            priority_order=self.priority_groups,
        )
        pdf_url_value = self._select_field(
            papers,
            "pdf_url",
            self._is_non_empty,
            priority_order=self.priority_groups,
        )
        is_oa_value = self._select_field(
            papers, "is_oa", self._is_not_none, priority_order=self.priority_groups
        )
        authors_value = self._select_field(
            papers,
            "authors",
            self._has_authors,
            priority_order=self._normalize_priority_spec(
                (("openalex", "semanticscholar"), *self.priority_groups)
            ),
            tie_breaker=self._prefer_more_authors,
        )

        primary_source = papers[primary_index].source

        return Paper(
            paper_id=paper_id_value or doi_value or papers[primary_index].paper_id,
            title=title_value or "",
            doi=doi_value,
            abstract=abstract_value,
            year=year_value,
            venue=venue_value,
            source=primary_source,
            url=url_value,
            pdf_url=pdf_url_value,
            is_oa=is_oa_value,
            authors=authors_value or [],
        )

    def _rank_key(self, paper: Paper, position: int) -> Tuple[int, int, int]:
        doi_rank = 0 if normalize_doi(paper.doi) else 1
        source_rank = self._source_rank(paper.source, self.priority_groups)
        return (doi_rank, source_rank, position)

    def _source_rank(self, source: str, priority_order: PrioritySpec) -> int:
        for idx, entry in enumerate(priority_order):
            if isinstance(entry, (list, tuple, set)):
                if source in entry:
                    return idx
            elif source == entry:
                return idx
        return len(priority_order)

    def _primary_source_index(self, papers: Sequence[Paper]) -> int:
        ranked = list(enumerate(papers))
        ranked.sort(key=lambda pair: self._rank_key(pair[1], pair[0]))
        return ranked[0][0]

    def _select_field(
        self,
        papers: Sequence[Paper],
        field_name: str,
        predicate,
        *,
        preferred_value: Any | None = None,
        priority_order: PrioritySpec | None = None,
        tie_breaker=None,
        transform=None,
    ) -> Any:
        selected_value: Any | None = None
        selected_rank: int | None = None
        selected_position: int | None = None

        priorities = priority_order or self.priority_groups

        for position, paper in enumerate(papers):
            raw_value = getattr(paper, field_name)
            value = transform(raw_value) if transform else raw_value

            if preferred_value is not None and value == preferred_value and predicate(value):
                return value

            if not predicate(value):
                continue

            rank = self._source_rank(paper.source, priorities)
            if selected_rank is None:
                selected_value = value
                selected_rank = rank
                selected_position = position
                continue

            better_candidate = False
            if rank < selected_rank:  # type: ignore[operator]
                better_candidate = True
            elif rank == selected_rank:
                if tie_breaker:
                    tie_decision = tie_breaker(selected_value, value)
                    if tie_decision is True:
                        better_candidate = True
                    elif tie_decision is False:
                        better_candidate = False
                    else:
                        better_candidate = position < (selected_position or 0)
                else:
                    better_candidate = position < (selected_position or 0)

            if better_candidate:
                selected_value = value
                selected_rank = rank
                selected_position = position
        return selected_value

    @staticmethod
    def _normalize_priority_spec(
        spec: PrioritySpec,
    ) -> PriorityGroups:
        normalized: List[Tuple[str, ...]] = []
        seen: set[str] = set()

        for entry in spec:
            if isinstance(entry, (list, tuple, set)):
                group = tuple(source for source in entry if source not in seen)
            else:
                group = (entry,) if entry not in seen else ()

            if group:
                normalized.append(group)
                seen.update(group)

        return tuple(normalized)

    @staticmethod
    def _is_non_empty(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    @staticmethod
    def _is_not_none(value: Any) -> bool:
        return value is not None

    @staticmethod
    def _has_authors(value: Any) -> bool:
        return bool(value)

    @staticmethod
    def _prefer_longer_text(current: Any, candidate: Any) -> bool:
        if current is None:
            return True
        if candidate is None:
            return False
        return len(str(candidate)) > len(str(current))

    @staticmethod
    def _prefer_more_authors(current: Any, candidate: Any) -> bool:
        current_len = len(current or [])
        candidate_len = len(candidate or [])
        return candidate_len > current_len


def merge_papers(papers: List[Paper]) -> Paper:
    """Convenience wrapper for merging without instantiating the service."""

    return PaperMergeService().merge(papers)
