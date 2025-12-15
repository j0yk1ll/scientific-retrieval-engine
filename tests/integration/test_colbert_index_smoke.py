from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from retrieval.index.colbert import ColbertIndex


def _colbert_available() -> bool:
    try:
        importlib.import_module("colbert")
        importlib.import_module("torch")
        return True
    except ModuleNotFoundError:
        return False


pytestmark = pytest.mark.skipif(
    not _colbert_available(),
    reason="colbert-ai (and torch) must be installed to run ColBERT smoke tests",
)


class _DummyContext:
    def __init__(self, _config):
        self._config = _config

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyRun:
    def context(self, config):
        return _DummyContext(config)


class _DummyIndexer:
    def __init__(self, checkpoint, config):
        self.checkpoint = checkpoint
        self.config = config
        self.calls = []

    def index(self, name, collection, overwrite=False):
        self.calls.append((name, collection, overwrite))


class _DummySearcher:
    def __init__(self, index, config):
        self.index = index
        self.config = config

    def search(self, query, k=10):
        return SimpleNamespace(docids=[0, 1], scores=[1.0, 0.5])


def test_build_and_search(monkeypatch, tmp_path):
    colbert_mod = importlib.import_module("colbert")
    infra_mod = importlib.import_module("colbert.infra")

    monkeypatch.setattr(colbert_mod, "Indexer", _DummyIndexer)
    monkeypatch.setattr(colbert_mod, "Searcher", _DummySearcher)
    monkeypatch.setattr(infra_mod, "Run", _DummyRun)
    monkeypatch.setattr(infra_mod, "RunConfig", lambda **kwargs: kwargs)
    monkeypatch.setattr(infra_mod, "ColBERTConfig", lambda **kwargs: kwargs)

    chunks = [("chunk-0", "hello world"), ("chunk-1", "another chunk")]
    index = ColbertIndex(index_dir=tmp_path, index_name="demo")

    index_path = index.build_index(chunks)
    assert (tmp_path / "demo.tsv").exists()
    assert index_path == tmp_path / "demo"

    results = index.search("hello", top_k=2)
    assert results == [("chunk-0", 1.0), ("chunk-1", 0.5)]
