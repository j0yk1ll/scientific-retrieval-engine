from __future__ import annotations

from typing import Sequence

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
