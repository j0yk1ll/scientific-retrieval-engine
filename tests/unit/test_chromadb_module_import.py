import importlib

import pytest

from retrieval.index import ChromaIndex


def test_missing_chromadb_raises_index_error(monkeypatch, tmp_path):
    def fake_import(name, *args, **kwargs):
        if name.startswith("chromadb"):
            raise ModuleNotFoundError("chromadb")
        return importlib.import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    index = ChromaIndex(
        index_dir=tmp_path,
        collection_name="test-index",
        chroma_url="http://localhost:8000",
    )

    with pytest.raises(IndexError) as excinfo:
        index.build_index([("c1", "text")])

    assert "pip install chromadb" in str(excinfo.value)
