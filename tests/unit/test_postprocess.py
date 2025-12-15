from retrieval.retrieval.postprocess import (
    deduplicate_chunks,
    diversify_by_paper,
    filter_min_score,
    postprocess_results,
)
from retrieval.retrieval.types import ChunkSearchResult


def make_result(chunk_id: int, paper_id: int, score: float) -> ChunkSearchResult:
    return ChunkSearchResult(
        chunk_id=chunk_id,
        paper_id=paper_id,
        chunk_order=0,
        content=f"chunk-{chunk_id}",
        score=score,
    )


def test_filter_min_score():
    results = [make_result(1, 10, 0.4), make_result(2, 11, 0.9)]

    filtered = filter_min_score(results, min_score=0.5)

    assert [item.chunk_id for item in filtered] == [2]


def test_deduplicate_chunks_preserves_first_occurrence():
    results = [make_result(1, 10, 0.2), make_result(1, 10, 0.5), make_result(2, 11, 0.3)]

    unique = deduplicate_chunks(results)

    assert [item.chunk_id for item in unique] == [1, 2]
    assert unique[0].score == 0.2


def test_diversify_by_paper_caps_results():
    results = [
        make_result(1, 10, 0.9),
        make_result(2, 10, 0.8),
        make_result(3, 11, 0.7),
        make_result(4, 10, 0.6),
    ]

    diversified = diversify_by_paper(results, max_per_paper=2)

    assert [item.chunk_id for item in diversified] == [1, 2, 3]


def test_postprocess_results_applies_all_steps():
    results = [
        make_result(1, 10, 0.9),
        make_result(2, 10, 0.3),
        make_result(2, 10, 0.4),
        make_result(3, 11, 0.2),
        make_result(4, 12, 0.8),
    ]

    processed = postprocess_results(results, min_score=0.25, max_per_paper=1)

    assert [item.chunk_id for item in processed] == [1, 4]
    assert processed[0].paper_id == 10
    assert processed[1].paper_id == 12
