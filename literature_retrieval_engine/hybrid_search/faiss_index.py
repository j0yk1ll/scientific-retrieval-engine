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
        self._dim: int | None = None
        self._normalized: bool | None = None
        self._metadata: dict[str, Any] | None = None

    def _ensure_index(self, dimension: int) -> None:
        if self._index is None:
            self._index = self._faiss.IndexFlatIP(dimension)
            self._dim = dimension
        elif self._dim is None:
            self._dim = dimension
        elif self._dim is not None and dimension != self._dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._dim}, got {dimension}"
            )

    def add(self, chunk: Chunk) -> None:
        self.add_many([chunk])

    def add_many(self, chunks: Iterable[Chunk]) -> None:
        chunk_list = list(chunks)
        if not chunk_list:
            return

        vectors = self._embed_texts([chunk.text for chunk in chunk_list])
        if vectors.ndim != 2:
            raise ValueError("Embedding output must be a 2D matrix.")

        vector_dim = vectors.shape[1]
        self._ensure_index(vector_dim)
        if self._dim is None:
            raise ValueError("FAISS index dimension is not initialized.")
        if vector_dim != self._dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._dim}, got {vector_dim}"
            )

        if self._index is None:
            raise ValueError("FAISS index is not initialized.")

        self._index.add(vectors)
        self._chunks.extend(chunk_list)
        self._record_metadata(vector_dim)

    def search(self, query: str, *, k: int = 10) -> List[Tuple[Chunk, float]]:
        if not query:
            return []
        if self._index is None or self._dim is None:
            raise ValueError("FAISS index is not initialized. Add vectors before searching.")
        if not self._chunks:
            return []

        query_vector = self._embed_texts([query])
        query_dim = query_vector.shape[1]
        if self._dim is not None and query_dim != self._dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._dim}, got {query_dim}"
            )
        search_k = min(k, len(self._chunks))
        scores, indices = self._index.search(query_vector, search_k)

        results: List[Tuple[Chunk, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((self._chunks[idx], float(score)))
        return results

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        embeddings = self.embedder.embed(texts)
        matrix = np.array(embeddings, dtype="float32")
        if self._normalized is None:
            self._normalized = self.normalize
        elif self._normalized != self.normalize:
            raise ValueError(
                "Cannot mix normalized and unnormalized vectors within the same index. "
                f"Existing vectors normalized={self._normalized}, "
                f"requested normalize={self.normalize}."
            )
        if self.normalize:
            self._faiss.normalize_L2(matrix)
        return matrix

    @property
    def metadata(self) -> dict[str, Any] | None:
        if self._metadata is None:
            return None
        return dict(self._metadata)

    def _record_metadata(self, dimension: int) -> None:
        if self._normalized is None:
            return
        embedder_name = (
            getattr(self.embedder, "model_name", None)
            or getattr(self.embedder, "model", None)
            or self.embedder.__class__.__name__
        )
        metadata = {
            "dimension": dimension,
            "normalized": self._normalized,
            "embedder": embedder_name,
        }
        if self._metadata is None:
            self._metadata = metadata
            return
        self._metadata.update(metadata)


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
