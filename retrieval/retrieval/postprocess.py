"""Postprocessing helpers for ranked search results."""

from __future__ import annotations

from typing import Iterable, Sequence

from retrieval.retrieval.types import ChunkSearchResult


def filter_min_score(
    results: Sequence[ChunkSearchResult], *, min_score: float | None
) -> list[ChunkSearchResult]:
    """Filter out results that do not meet ``min_score``.

    When ``min_score`` is ``None`` the input sequence is returned unchanged.
    """

    if min_score is None:
        return list(results)
    return [result for result in results if result.score >= min_score]


def deduplicate_chunks(results: Iterable[ChunkSearchResult]) -> list[ChunkSearchResult]:
    """Remove duplicate chunk identifiers while preserving order."""

    seen: set[int] = set()
    unique: list[ChunkSearchResult] = []
    for result in results:
        if result.chunk_id in seen:
            continue
        seen.add(result.chunk_id)
        unique.append(result)
    return unique


def diversify_by_paper(
    results: Iterable[ChunkSearchResult], *, max_per_paper: int
) -> list[ChunkSearchResult]:
    """Limit the number of chunks returned per paper.

    Ordering is preserved while truncating additional chunks beyond
    ``max_per_paper`` for each ``paper_id``.
    """

    if max_per_paper <= 0:
        return []

    counts: dict[int, int] = {}
    diversified: list[ChunkSearchResult] = []

    for result in results:
        count = counts.get(result.paper_id, 0)
        if count >= max_per_paper:
            continue
        counts[result.paper_id] = count + 1
        diversified.append(result)

    return diversified


def postprocess_results(
    results: Sequence[ChunkSearchResult],
    *,
    min_score: float | None = None,
    max_per_paper: int = 2,
) -> list[ChunkSearchResult]:
    """Apply filtering, deduplication, and diversification to ranked results."""

    filtered = filter_min_score(results, min_score=min_score)
    unique = deduplicate_chunks(filtered)
    return diversify_by_paper(unique, max_per_paper=max_per_paper)
