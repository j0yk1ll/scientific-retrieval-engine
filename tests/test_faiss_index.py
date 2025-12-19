from __future__ import annotations

import numpy as np
import pytest

from retrieval.hybrid_search.faiss_index import FaissVectorIndex
from retrieval.hybrid_search.models import Chunk


class CountingEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts):
        call = list(texts)
        self.calls.append(call)
        return [[float(i + 1), float(i + 1)] for i, _ in enumerate(call)]


class DummyFaissIndex:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.vectors: list[np.ndarray] = []

    def add(self, vectors):
        arr = np.array(vectors, dtype="float32")
        self.vectors.extend(arr)

    def search(self, vectors, k):
        query = np.array(vectors, dtype="float32")[0]
        scores = [float(np.dot(vec, query)) for vec in self.vectors]
        order = np.argsort(scores)[::-1]
        top_k = order[:k]

        scores_arr = np.full(k, -1.0, dtype="float32")
        indices_arr = np.full(k, -1, dtype="int64")
        for out_idx, vec_idx in enumerate(top_k):
            scores_arr[out_idx] = scores[vec_idx]
            indices_arr[out_idx] = vec_idx
        return scores_arr.reshape(1, -1), indices_arr.reshape(1, -1)


def _make_dummy_faiss():
    class DummyFaissModule:
        def __init__(self) -> None:
            self.created: list[DummyFaissIndex] = []

        def IndexFlatIP(self, dimension: int) -> DummyFaissIndex:
            index = DummyFaissIndex(dimension)
            self.created.append(index)
            return index

        @staticmethod
        def normalize_L2(matrix):  # pragma: no cover - normalization is optional here
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matrix /= norms

    return DummyFaissModule()


def test_faiss_index_batches_embeddings(monkeypatch):
    embedder = CountingEmbedder()
    dummy_faiss = _make_dummy_faiss()
    monkeypatch.setattr("retrieval.hybrid_search.faiss_index._load_faiss", lambda: dummy_faiss)

    index = FaissVectorIndex(embedder, normalize=False)
    chunks = [
        Chunk(chunk_id="c1", paper_id="p1", text="first"),
        Chunk(chunk_id="c2", paper_id="p2", text="second"),
    ]

    index.add_many(chunks)

    assert embedder.calls[0] == ["first", "second"]
    assert dummy_faiss.created and dummy_faiss.created[0].dimension == 2
    assert len(dummy_faiss.created[0].vectors) == 2

    results = index.search("second", k=2)

    assert len(results) == 2
    assert results[0][0].chunk_id == "c2"
    assert embedder.calls[-1] == ["second"]


def test_faiss_index_reports_normalization_conflict(monkeypatch):
    embedder = CountingEmbedder()
    dummy_faiss = _make_dummy_faiss()
    monkeypatch.setattr("retrieval.hybrid_search.faiss_index._load_faiss", lambda: dummy_faiss)

    index = FaissVectorIndex(embedder, normalize=True)
    index.add(Chunk(chunk_id="c1", paper_id="p1", text="first"))

    index.normalize = False
    with pytest.raises(
        ValueError,
        match="Existing vectors normalized=True, requested normalize=False",
    ):
        index.add(Chunk(chunk_id="c2", paper_id="p2", text="second"))


def test_faiss_index_records_metadata(monkeypatch):
    embedder = CountingEmbedder()
    dummy_faiss = _make_dummy_faiss()
    monkeypatch.setattr("retrieval.hybrid_search.faiss_index._load_faiss", lambda: dummy_faiss)

    index = FaissVectorIndex(embedder, normalize=True)
    index.add(Chunk(chunk_id="c1", paper_id="p1", text="first"))

    assert index.metadata == {
        "dimension": 2,
        "normalized": True,
        "embedder": "CountingEmbedder",
    }
