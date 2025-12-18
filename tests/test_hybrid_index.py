from __future__ import annotations

from typing import Sequence

import pytest

from retrieval.chunking import GrobidChunk
from retrieval.hybrid import (
    BM25Index,
    Chunk,
    FaissVectorIndex,
    HybridRetrievalConfig,
    HybridRetriever,
)


class StaticEmbedder:
    def __init__(self, mapping: dict[str, Sequence[float]], default: Sequence[float]):
        self.mapping = mapping
        self.default = default

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        vectors = []
        for text in texts:
            for key, vector in self.mapping.items():
                if key in text:
                    vectors.append(vector)
                    break
            else:
                vectors.append(self.default)
        return vectors


class VariableDimEmbedder:
    def __init__(self, mismatch_on: str, base_dim: int = 1):
        self.mismatch_on = mismatch_on
        self.base_dim = base_dim

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        vectors: list[Sequence[float]] = []
        for text in texts:
            if text == self.mismatch_on:
                vectors.append([0.0] * (self.base_dim + 1))
            else:
                vectors.append([0.0] * self.base_dim)
        return vectors


class CountingEmbedder(StaticEmbedder):
    def __init__(self, mapping: dict[str, Sequence[float]], default: Sequence[float]):
        super().__init__(mapping, default)
        self.call_count = 0

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.call_count += 1
        return super().embed(texts)


def test_bm25_prioritizes_lexical_match():
    bm25 = BM25Index()
    chunks = [
        Chunk(chunk_id="1", paper_id="p1", text="machine learning for health"),
        Chunk(chunk_id="2", paper_id="p2", text="cooking recipes and ingredients"),
    ]
    bm25.add_many(chunks)

    results = bm25.search("machine learning", k=1)

    assert results[0][0].chunk_id == "1"
    assert results[0][1] > 0


def test_bm25_tokenizer_splits_punctuation():
    bm25 = BM25Index()

    tokens = bm25.tokenizer("AI-based, health-care: systems!!!")

    assert tokens == ["ai", "based", "health", "care", "systems"]


def test_bm25_search_matches_without_punctuation_exactness():
    bm25 = BM25Index()
    chunks = [
        Chunk(
            chunk_id="1",
            paper_id="p1",
            text="Breakthrough in AI-based, health-care: systems.",
        ),
    ]
    bm25.add_many(chunks)

    results = bm25.search("AI based health care systems")

    assert results
    assert results[0][0].chunk_id == "1"


def test_bm25_avg_length_and_query_term_frequency():
    bm25 = BM25Index(include_query_term_frequency=True)
    chunks = [
        Chunk(chunk_id="1", paper_id="p1", text="apple apple"),
        Chunk(chunk_id="2", paper_id="p2", text="banana"),
    ]
    bm25.add_many(chunks)

    assert bm25._total_doc_len == 3
    assert bm25._avg_doc_len == pytest.approx(1.5)

    results = bm25.search("apple apple banana", k=2)

    assert results
    assert results[0][0].chunk_id == "1"


def test_hybrid_prefers_semantic_match_when_lexical_absent():
    embedder = StaticEmbedder(
        {
            "myocardial infarction": [1.0, 0.0],
            "quick brown": [0.0, 1.0],
            "heart attack": [1.0, 0.0],
        },
        default=[0.0, 0.0],
    )
    vector_index = FaissVectorIndex(embedder)
    bm25 = BM25Index()
    hybrid = HybridRetriever(
        bm25,
        vector_index,
        config=HybridRetrievalConfig(bm25_weight=0.5, vector_weight=2.0, limit=2),
    )

    grobid_chunks = [
        GrobidChunk(
            chunk_id="chunk-1",
            paper_id="p1",
            section="Background",
            content="The quick brown fox.",
            stream_start_char=0,
            stream_end_char=10,
            token_count=4,
            section_index=0,
        ),
        GrobidChunk(
            chunk_id="chunk-2",
            paper_id="p2",
            section="Cardiology",
            content="Treatment for myocardial infarction improves outcomes.",
            stream_start_char=11,
            stream_end_char=70,
            token_count=7,
            section_index=1,
        ),
    ]

    chunks = [Chunk.from_grobid(chunk) for chunk in grobid_chunks]
    hybrid.index_chunks(chunks)

    semantic_query = "heart attack treatment"
    results = hybrid.search(semantic_query)

    assert results
    assert results[0].chunk.chunk_id == "chunk-2"
    assert results[0].vector_raw_score is not None
    assert (
        results[0].lexical_raw_score is None
        or results[0].lexical_raw_score <= results[0].vector_raw_score
    )


class StaticIndex:
    def __init__(self, hits: list[tuple[Chunk, float]]):
        self.hits = hits

    def add_many(self, chunks: Sequence[Chunk]) -> None:  # pragma: no cover - stub
        return None

    def search(self, query: str, k: int = 10) -> list[tuple[Chunk, float]]:
        return self.hits[:k]


def test_rrf_fusion_orders_by_rank_not_magnitude():
    chunks = [
        Chunk(chunk_id="a", paper_id="p1", text="high lexical"),
        Chunk(chunk_id="b", paper_id="p2", text="high vector"),
    ]

    bm25_hits = [(chunks[0], 1000.0), (chunks[1], 0.01)]
    vector_hits = [(chunks[1], 0.1), (chunks[0], 0.001)]

    hybrid = HybridRetriever(
        StaticIndex(bm25_hits),
        StaticIndex(vector_hits),
        config=HybridRetrievalConfig(bm25_weight=0.1, vector_weight=2.0, limit=2),
    )

    results = hybrid.search("query")

    assert results[0].chunk.chunk_id == "b"
    assert results[0].fused_score > results[1].fused_score


def test_retrieval_result_contains_ranks_when_enabled():
    chunks = [
        Chunk(chunk_id="a", paper_id="p1", text="high lexical"),
        Chunk(chunk_id="b", paper_id="p2", text="high vector"),
    ]

    bm25_hits = [(chunks[0], 10.0), (chunks[1], 1.0)]
    vector_hits = [(chunks[1], 0.1), (chunks[0], 0.01)]

    hybrid = HybridRetriever(
        StaticIndex(bm25_hits),
        StaticIndex(vector_hits),
        config=HybridRetrievalConfig(
            include_ranks=True, bm25_weight=0.1, vector_weight=2.0, limit=2
        ),
    )

    results = hybrid.search("query")

    assert results[0].chunk.chunk_id == "b"
    assert results[0].lexical_rank == 2
    assert results[0].vector_rank == 1
    assert results[0].lexical_raw_score == 1.0
    assert results[0].vector_raw_score == 0.1


def test_faiss_add_many_batches_embeddings_once():
    embedder = CountingEmbedder(
        {
            "alpha": [1.0, 0.0],
            "beta": [0.0, 1.0],
        },
        default=[0.0, 0.0],
    )
    index = FaissVectorIndex(embedder)

    chunks = [
        Chunk(chunk_id="1", paper_id="p1", text="alpha study"),
        Chunk(chunk_id="2", paper_id="p2", text="beta analysis"),
    ]

    index.add_many(chunks)

    assert embedder.call_count == 1

    results = index.search("alpha query", k=2)

    assert [chunk.chunk_id for chunk, _ in results] == ["1", "2"]


def test_faiss_sets_dim_on_first_ensure_index():
    embedder = StaticEmbedder({}, default=[0.0, 0.0])
    index = FaissVectorIndex(embedder)

    assert index._dim is None

    index._ensure_index(2)

    assert index._dim == 2


def test_faiss_raises_on_dim_mismatch_add():
    embedder = VariableDimEmbedder(mismatch_on="bad")
    index = FaissVectorIndex(embedder)

    index.add(Chunk(chunk_id="1", paper_id="p1", text="ok"))

    with pytest.raises(ValueError, match=r"expected 1, got 2"):
        index.add(Chunk(chunk_id="2", paper_id="p2", text="bad"))


def test_faiss_add_many_raises_on_dim_mismatch():
    embedder = VariableDimEmbedder(mismatch_on="bad")
    index = FaissVectorIndex(embedder)

    index.add_many([Chunk(chunk_id="1", paper_id="p1", text="ok")])

    with pytest.raises(ValueError, match=r"expected 1, got 2"):
        index.add_many([Chunk(chunk_id="2", paper_id="p2", text="bad")])

    assert len(index._chunks) == 1


def test_faiss_raises_on_dim_mismatch_search_query_vector():
    embedder = VariableDimEmbedder(mismatch_on="bad")
    index = FaissVectorIndex(embedder)

    index.add(Chunk(chunk_id="1", paper_id="p1", text="ok"))

    with pytest.raises(ValueError, match=r"expected 1, got 2"):
        index.search("bad")
