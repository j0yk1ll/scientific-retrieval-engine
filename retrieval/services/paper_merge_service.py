from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

from retrieval.identifiers import normalize_doi
from retrieval.models import Paper, PaperEvidence, PaperProvenance


DEFAULT_SOURCE_PRIORITY = ("crossref", "datacite", "openalex", "semanticscholar")

PrioritySpec = Sequence[str | Sequence[str]]
PriorityGroups = Tuple[Tuple[str, ...], ...]


class PaperMergeService:
    """Merge multiple records for the same paper into a single enriched record."""

    def __init__(self, *, source_priority: PrioritySpec | None = None) -> None:
        self.priority_groups: PriorityGroups = self._normalize_priority_spec(
            source_priority or DEFAULT_SOURCE_PRIORITY
        )
        self.flat_priority_order: Tuple[str, ...] = tuple(
            source for group in self.priority_groups for source in group
        )
        self.source_priority: Dict[str, int] = {}
        for idx, group in enumerate(self.priority_groups):
            for source in group:
                self.source_priority[source] = idx

    def merge(self, papers: List[Paper]) -> Paper:
        if not papers:
            raise ValueError("Cannot merge an empty collection of papers")

        primary_index = self._primary_source_index(papers)
        provenance = self._build_provenance(papers)

        field_priorities = {
            "doi": self.priority_groups,
            "year": self.priority_groups,
            "venue": self.priority_groups,
            "url": self.priority_groups,
            "abstract": self._normalize_priority_spec(
                (("openalex", "semanticscholar"), *self.priority_groups)
            ),
            "authors": self._normalize_priority_spec(
                (("openalex", "semanticscholar"), *self.priority_groups)
            ),
        }

        selections: Dict[str, Tuple[Any, PaperEvidence | None]] = {}

        doi_value, doi_evidence = self._select_field(
            papers,
            "doi",
            self._is_non_empty,
            priority_order=field_priorities["doi"],
            transform=normalize_doi,
        )
        selections["doi"] = (doi_value, doi_evidence)

        selections["paper_id"] = self._select_field(
            papers,
            "paper_id",
            self._is_non_empty,
            preferred_value=doi_value,
            priority_order=self.priority_groups,
        )

        selections["title"] = self._select_field(
            papers, "title", self._is_non_empty, priority_order=self.priority_groups
        )
        selections["abstract"] = self._select_field(
            papers,
            "abstract",
            self._is_non_empty,
            priority_order=field_priorities["abstract"],
            tie_breaker=self._prefer_longer_text,
        )
        selections["year"] = self._select_field(
            papers, "year", self._is_not_none, priority_order=field_priorities["year"]
        )
        selections["venue"] = self._select_field(
            papers, "venue", self._is_non_empty, priority_order=field_priorities["venue"]
        )
        selections["url"] = self._select_field(
            papers, "url", self._is_non_empty, priority_order=field_priorities["url"]
        )
        selections["pdf_url"] = self._select_field(
            papers,
            "pdf_url",
            self._is_non_empty,
            priority_order=self.priority_groups,
        )
        selections["is_oa"] = self._select_field(
            papers, "is_oa", self._is_not_none, priority_order=self.priority_groups
        )
        selections["authors"] = self._select_field(
            papers,
            "authors",
            self._has_authors,
            priority_order=field_priorities["authors"],
            tie_breaker=self._prefer_more_authors,
        )

        primary_source = self._determine_primary_source(
            selections, fallback_source=papers[primary_index].source
        )

        merged = Paper(
            paper_id=selections["paper_id"][0] or doi_value or papers[primary_index].paper_id,
            title=selections["title"][0] or "",
            doi=doi_value,
            abstract=selections["abstract"][0],
            year=selections["year"][0],
            venue=selections["venue"][0],
            source=primary_source,
            primary_source=primary_source,
            url=selections["url"][0],
            pdf_url=selections["pdf_url"][0],
            is_oa=selections["is_oa"][0],
            authors=selections["authors"][0] or [],
            provenance=provenance,
        )

        self._record_field_sources(
            selections,
            provenance,
            {
                "paper_id": self._is_non_empty,
                "title": self._is_non_empty,
                "abstract": self._is_non_empty,
                "year": self._is_not_none,
                "venue": self._is_non_empty,
                "url": self._is_non_empty,
                "pdf_url": self._is_non_empty,
                "is_oa": self._is_not_none,
                "authors": self._has_authors,
                "doi": self._is_non_empty,
            },
        )

        return merged

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

    def _build_provenance(self, papers: Iterable[Paper]) -> PaperProvenance:
        sources: List[str] = []
        source_records: Dict[str, str] = {}
        for paper in papers:
            if paper.source not in sources:
                sources.append(paper.source)
            if paper.paper_id:
                source_records.setdefault(paper.source, paper.paper_id)
        return PaperProvenance(sources=sources, source_records=source_records)

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
    ) -> Tuple[Any, PaperEvidence | None]:
        selected_value: Any | None = None
        selected_evidence: PaperEvidence | None = None
        selected_rank: int | None = None
        selected_position: int | None = None

        priorities = priority_order or self.priority_groups

        for position, paper in enumerate(papers):
            raw_value = getattr(paper, field_name)
            value = transform(raw_value) if transform else raw_value

            if preferred_value is not None and value == preferred_value and predicate(value):
                return value, PaperEvidence(source=paper.source, value=value)

            if not predicate(value):
                continue

            rank = self._source_rank(paper.source, priorities)
            if selected_evidence is None:
                selected_value = value
                selected_evidence = PaperEvidence(source=paper.source, value=value)
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
                        better_candidate = position < selected_position  # type: ignore[operator]
                else:
                    better_candidate = position < selected_position  # type: ignore[operator]

            if better_candidate:
                selected_value = value
                selected_evidence = PaperEvidence(source=paper.source, value=value)
                selected_rank = rank
                selected_position = position
        return selected_value, selected_evidence

    def _determine_primary_source(
        self,
        selections: Dict[str, Tuple[Any, PaperEvidence | None]],
        *,
        fallback_source: str,
    ) -> str:
        identifier_fields = ("doi", "title", "paper_id")
        for field_name in identifier_fields:
            value, evidence = selections.get(field_name, (None, None))
            if evidence and self._is_non_empty(value):
                return evidence.source

        counts: Dict[str, int] = {}
        for value, evidence in selections.values():
            if evidence:
                counts[evidence.source] = counts.get(evidence.source, 0) + 1

        if counts:
            sorted_sources = sorted(
                counts.items(),
                key=lambda item: (
                    -item[1],
                    self._source_rank(item[0], self.priority_groups),
                    item[0],
                ),
            )
            return sorted_sources[0][0]

        return fallback_source

    def _record_field_sources(
        self,
        selections: Dict[str, Tuple[Any, PaperEvidence | None]],
        provenance: PaperProvenance,
        field_predicates: Dict[str, Any],
    ) -> None:
        for field_name, predicate in field_predicates.items():
            value, evidence = selections.get(field_name, (None, None))
            if evidence and predicate(value):
                provenance.field_sources[field_name] = evidence

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
