"""Dataclasses describing retrieval search results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Tuple

from retrieval.storage.models import Paper


@dataclass(frozen=True)
class ChunkSearchResult:
    """A ranked chunk returned from the search index."""

    chunk_id: str  # Now uses the stable chunk_id string
    db_id: int  # Database primary key
    paper_id: int  # Database FK to papers
    paper_uuid: str  # Paper's stable UUID
    kind: str
    position: int
    section_title: str | None
    order_in_section: int | None
    content: str
    score: float
    citations: tuple[str, ...] = field(default_factory=tuple)
    language: str | None = None


@dataclass(frozen=True)
class EvidencePaper:
    """A paper paired with the supporting chunks returned by search."""

    paper: Paper
    chunks: Tuple[ChunkSearchResult, ...] = field(default_factory=tuple)

    def top_chunks(self, limit: int) -> Tuple[ChunkSearchResult, ...]:
        """Return the top ``limit`` chunks for the paper, preserving order."""

        if limit <= 0:
            return tuple()
        return self.chunks[:limit]


@dataclass(frozen=True)
class EvidenceBundle:
    """Container for an aggregated search response."""

    query: str
    papers: Tuple[EvidencePaper, ...] = field(default_factory=tuple)

    def all_chunks(self) -> Tuple[ChunkSearchResult, ...]:
        """Flatten all chunk evidence in ranking order."""

        flattened: list[ChunkSearchResult] = []
        for paper in self.papers:
            flattened.extend(paper.chunks)
        return tuple(flattened)

    @classmethod
    def from_chunks(
        cls,
        query: str,
        paper_map: dict[int, Paper],
        chunk_results: Iterable[ChunkSearchResult],
    ) -> "EvidenceBundle":
        """Group ranked chunks into paper-level evidence bundles."""

        grouped: dict[int, list[ChunkSearchResult]] = {}
        for result in chunk_results:
            grouped.setdefault(result.paper_id, []).append(result)

        papers: list[EvidencePaper] = []
        for paper_id, paper_chunks in grouped.items():
            paper = paper_map.get(paper_id)
            if paper is None:
                continue
            papers.append(EvidencePaper(paper=paper, chunks=tuple(paper_chunks)))

        return cls(query=query, papers=tuple(papers))
