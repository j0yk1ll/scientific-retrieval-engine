from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

from retrieval.identifiers import normalize_doi
from retrieval.models import Paper, PaperEvidence, PaperProvenance


class PaperMergeService:
    """Merge multiple records for the same paper into a single enriched record."""

    def __init__(self, *, source_priority: Sequence[str] | None = None) -> None:
        self.source_priority = {source: idx for idx, source in enumerate(source_priority or [])}

    def merge(self, papers: List[Paper]) -> Paper:
        if not papers:
            raise ValueError("Cannot merge an empty collection of papers")

        ranked = list(enumerate(papers))
        ranked.sort(key=lambda pair: self._rank_key(pair[1], pair[0]))

        provenance = self._build_provenance(papers)

        doi_value, doi_evidence = self._select_field(ranked, "doi", self._is_non_empty)
        paper_id_value, _ = self._select_field(
            ranked, "paper_id", self._is_non_empty, preferred_value=doi_value
        )

        merged = Paper(
            paper_id=paper_id_value or doi_value or papers[0].paper_id,
            title=self._select_field(ranked, "title", self._is_non_empty)[0] or "",
            doi=doi_value,
            abstract=self._select_field(ranked, "abstract", self._is_non_empty)[0],
            year=self._select_field(ranked, "year", self._is_not_none)[0],
            venue=self._select_field(ranked, "venue", self._is_non_empty)[0],
            source=(doi_evidence.source if doi_evidence else ranked[0][1].source),
            url=self._select_field(ranked, "url", self._is_non_empty)[0],
            pdf_url=self._select_field(ranked, "pdf_url", self._is_non_empty)[0],
            is_oa=self._select_field(ranked, "is_oa", self._is_not_none)[0],
            authors=self._select_field(ranked, "authors", self._has_authors)[0] or [],
            provenance=provenance,
        )

        if doi_evidence:
            provenance.field_sources["doi"] = doi_evidence

        self._record_field_sources(
            ranked,
            provenance,
            {
                "title": self._is_non_empty,
                "abstract": self._is_non_empty,
                "year": self._is_not_none,
                "venue": self._is_non_empty,
                "url": self._is_non_empty,
                "pdf_url": self._is_non_empty,
                "is_oa": self._is_not_none,
                "authors": self._has_authors,
            },
        )

        return merged

    def _rank_key(self, paper: Paper, position: int) -> Tuple[int, int, int]:
        doi_rank = 0 if normalize_doi(paper.doi) else 1
        source_rank = self.source_priority.get(paper.source, len(self.source_priority))
        return (doi_rank, source_rank, position)

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
        ranked: List[Tuple[int, Paper]],
        field_name: str,
        predicate,
        *,
        preferred_value: Any | None = None,
    ) -> Tuple[Any, PaperEvidence | None]:
        if preferred_value and predicate(preferred_value):
            for _, paper in ranked:
                if getattr(paper, field_name) == preferred_value:
                    return preferred_value, PaperEvidence(source=paper.source, value=preferred_value)

        for _, paper in ranked:
            value = getattr(paper, field_name)
            if predicate(value):
                return value, PaperEvidence(source=paper.source, value=value)
        return None, None

    def _record_field_sources(
        self,
        ranked: List[Tuple[int, Paper]],
        provenance: PaperProvenance,
        field_predicates: Dict[str, Any],
    ) -> None:
        for field_name, predicate in field_predicates.items():
            if field_name in provenance.field_sources:
                continue
            _, evidence = self._select_field(ranked, field_name, predicate)
            if evidence:
                provenance.field_sources[field_name] = evidence

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


def merge_papers(papers: List[Paper]) -> Paper:
    """Convenience wrapper for merging without instantiating the service."""

    return PaperMergeService().merge(papers)

