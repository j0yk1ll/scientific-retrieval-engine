import importlib
from types import SimpleNamespace

import pytest

from retrieval.index import ChromaIndex


def _chromadb_available() -> bool:
    try:
        importlib.import_module("chromadb")
        return True
    except ModuleNotFoundError:
        return False


pytestmark = pytest.mark.skipif(
    not _chromadb_available(),
    reason="chromadb must be installed to run ChromaDB smoke tests",
)


class _DummyCollection:
    def __init__(self):
        self.upserts = []

    def upsert(self, ids, documents, metadatas):
        self.upserts.append((ids, documents, metadatas))

    def query(self, query_texts, n_results):
        ids = [chunk_id for stored_ids, *_ in self.upserts for chunk_id in stored_ids]
        return {"ids": [ids], "distances": [[0.1 for _ in ids]]}


class _DummyClient:
    collection = _DummyCollection()

    def __init__(self, path):
        self.path = path
        self.deleted = []
        self.collection = _DummyClient.collection

    def delete_collection(self, name):
        self.deleted.append(name)
        _DummyClient.collection = _DummyCollection()
        self.collection = _DummyClient.collection

    def get_or_create_collection(self, name, embedding_function=None):
        return self.collection


def test_build_and_search(monkeypatch, tmp_path):
    chromadb_mod = importlib.import_module("chromadb")
    embeddings_mod = importlib.import_module("chromadb.utils.embedding_functions")

    monkeypatch.setattr(chromadb_mod, "PersistentClient", _DummyClient)
    monkeypatch.setattr(
        embeddings_mod, "DefaultEmbeddingFunction", lambda: SimpleNamespace()
    )

    chunks = [("chunk-0", "hello world"), ("chunk-1", "another chunk")]
    index = ChromaIndex(index_dir=tmp_path, collection_name="demo")

    index_path = index.build_index(chunks)
    assert index_path == tmp_path

    results = index.search("hello", top_k=2)
    assert results == [("chunk-0", 0.9), ("chunk-1", 0.9)]
