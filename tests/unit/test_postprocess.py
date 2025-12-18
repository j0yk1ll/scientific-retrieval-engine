from retrieval.retrieval.postprocess import (
    deduplicate_chunks,
    diversify_by_paper,
    filter_min_score,
    postprocess_results,
)
from retrieval.retrieval.types import ChunkSearchResult


def make_result(chunk_id: int, paper_id: int, score: float) -> ChunkSearchResult:
    return ChunkSearchResult(
        chunk_id=f"paper-1:chunk:{chunk_id}",
        db_id=chunk_id,
        paper_id=paper_id,
        paper_uuid="paper-1",
        kind="section_paragraph",
        position=chunk_id,
        section_path=("body",),
        section_title=None,
        order_in_section=None,
        content=f"chunk-{chunk_id}",
        score=score,
    )


def test_filter_min_score():
    results = [make_result(1, 10, 0.4), make_result(2, 11, 0.9)]

    filtered = filter_min_score(results, min_score=0.5)

    assert [item.db_id for item in filtered] == [2]


def test_deduplicate_chunks_preserves_first_occurrence():
    # Create two results with the same chunk_id
    result1 = ChunkSearchResult(
        chunk_id="paper-1:chunk:1",
        db_id=1,
        paper_id=10,
        paper_uuid="paper-1",
        kind="section_paragraph",
        position=1,
        section_path=("body",),
        section_title=None,
        order_in_section=None,
        content="chunk-1",
        score=0.2,
    )
    result2 = ChunkSearchResult(
        chunk_id="paper-1:chunk:1",  # Same chunk_id
        db_id=1,
        paper_id=10,
        paper_uuid="paper-1",
        kind="section_paragraph",
        position=1,
        section_path=("body",),
        section_title=None,
        order_in_section=None,
        content="chunk-1",
        score=0.5,
    )
    result3 = make_result(2, 11, 0.3)
    results = [result1, result2, result3]

    unique = deduplicate_chunks(results)

    assert [item.db_id for item in unique] == [1, 2]
    assert unique[0].score == 0.2


def test_diversify_by_paper_caps_results():
    results = [
        make_result(1, 10, 0.9),
        make_result(2, 10, 0.8),
        make_result(3, 11, 0.7),
        make_result(4, 10, 0.6),
    ]

    diversified = diversify_by_paper(results, max_per_paper=2)

    assert [item.db_id for item in diversified] == [1, 2, 3]


def test_postprocess_results_applies_all_steps():
    results = [
        make_result(1, 10, 0.9),
        make_result(2, 10, 0.3),
        make_result(3, 11, 0.2),
        make_result(4, 12, 0.8),
    ]

    processed = postprocess_results(results, min_score=0.25, max_per_paper=1)

    assert [item.db_id for item in processed] == [1, 4]
    assert processed[0].paper_id == 10
    assert processed[1].paper_id == 12
