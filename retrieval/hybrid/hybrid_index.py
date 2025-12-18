from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .bm25_index import BM25Index
from .faiss_index import FaissVectorIndex
from .models import Chunk, RetrievedChunk


@dataclass
class HybridRetrievalConfig:
    bm25_weight: float = 1.0
    vector_weight: float = 1.0
    rrf_k: int = 60
    bm25_k: int = 10
    vector_k: int = 10
    limit: int = 10


class HybridRetriever:
    """Combine lexical BM25 search with FAISS-based vector search."""

    def __init__(
        self,
        bm25_index: BM25Index,
        vector_index: FaissVectorIndex,
        *,
        config: Optional[HybridRetrievalConfig] = None,
    ) -> None:
        self.bm25 = bm25_index
        self.vector = vector_index
        self.config = config or HybridRetrievalConfig()

    def index_chunks(self, chunks: Iterable[Chunk]) -> None:
        self.bm25.add_many(chunks)
        self.vector.add_many(chunks)

    def search(self, query: str) -> List[RetrievedChunk]:
        bm25_hits = self.bm25.search(query, k=self.config.bm25_k)
        vector_hits = self.vector.search(query, k=self.config.vector_k)

        fused: Dict[str, RetrievedChunk] = {}

        self._accumulate_scores(
            fused,
            bm25_hits,
            weight=self.config.bm25_weight,
            key="lexical_score",
        )
        self._accumulate_scores(
            fused,
            vector_hits,
            weight=self.config.vector_weight,
            key="vector_score",
        )

        results = sorted(fused.values(), key=lambda item: item.fused_score, reverse=True)
        return results[: self.config.limit]

    def _accumulate_scores(
        self,
        fused: Dict[str, RetrievedChunk],
        results: List[tuple[Chunk, float]],
        *,
        weight: float,
        key: str,
    ) -> None:
        for rank, (chunk, score) in enumerate(results, start=1):
            fused_score = weight / (self.config.rrf_k + rank)
            if chunk.chunk_id not in fused:
                fused[chunk.chunk_id] = RetrievedChunk(
                    chunk=chunk,
                    fused_score=fused_score,
                )
            else:
                fused[chunk.chunk_id].fused_score += fused_score
            setattr(fused[chunk.chunk_id], key, score)


__all__ = ["HybridRetriever", "HybridRetrievalConfig"]
