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
            start_char=0,
            end_char=10,
            token_count=4,
        ),
        GrobidChunk(
            chunk_id="chunk-2",
            paper_id="p2",
            section="Cardiology",
            content="Treatment for myocardial infarction improves outcomes.",
            start_char=11,
            end_char=70,
            token_count=7,
        ),
    ]

    chunks = [Chunk.from_grobid(chunk) for chunk in grobid_chunks]
    hybrid.index_chunks(chunks)

    semantic_query = "heart attack treatment"
    results = hybrid.search(semantic_query)

    assert results
    assert results[0].chunk.chunk_id == "chunk-2"
    assert results[0].vector_score is not None
    assert results[0].lexical_score is None or results[0].lexical_score <= results[0].vector_score


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


def test_faiss_raises_on_dim_mismatch_search_query_vector():
    embedder = VariableDimEmbedder(mismatch_on="bad")
    index = FaissVectorIndex(embedder)

    index.add(Chunk(chunk_id="1", paper_id="p1", text="ok"))

    with pytest.raises(ValueError, match=r"expected 1, got 2"):
        index.search("bad")
