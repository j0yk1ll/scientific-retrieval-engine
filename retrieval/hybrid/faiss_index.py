from __future__ import annotations

from typing import Any, Iterable, List, Tuple

import numpy as np

from .embeddings import Embedder
from .models import Chunk


class FaissVectorIndex:
    """Vector index built on FAISS with pluggable embeddings."""

    def __init__(self, embedder: Embedder, *, normalize: bool = True) -> None:
        self.embedder = embedder
        self.normalize = normalize
        self._faiss = _load_faiss()
        self._index: Any | None = None
        self._chunks: List[Chunk] = []

    def _ensure_index(self, dimension: int) -> None:
        if self._index is None:
            self._index = self._faiss.IndexFlatIP(dimension)

    def add(self, chunk: Chunk) -> None:
        vector = self._embed_texts([chunk.text])[0]
        self._ensure_index(len(vector))
        self._index.add(np.array([vector], dtype="float32"))
        self._chunks.append(chunk)

    def add_many(self, chunks: Iterable[Chunk]) -> None:
        for chunk in chunks:
            self.add(chunk)

    def search(self, query: str, *, k: int = 10) -> List[Tuple[Chunk, float]]:
        if not query or not self._chunks or self._index is None:
            return []

        query_vector = self._embed_texts([query])
        search_k = min(k, len(self._chunks))
        scores, indices = self._index.search(
            np.array(query_vector, dtype="float32"), search_k
        )

        results: List[Tuple[Chunk, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((self._chunks[idx], float(score)))
        return results

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        embeddings = self.embedder.embed(texts)
        matrix = np.array(embeddings, dtype="float32")
        if self.normalize:
            self._faiss.normalize_L2(matrix)
        return matrix


__all__ = ["FaissVectorIndex"]


def _load_faiss():
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "Hybrid retrieval requires the optional dependency 'faiss-cpu'. "
            "Install it with `pip install faiss-cpu`."
        ) from exc
    return faiss
