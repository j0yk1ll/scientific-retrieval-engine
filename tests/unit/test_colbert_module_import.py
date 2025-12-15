import importlib

import pytest

from retrieval.index.colbert import ColbertIndex


def test_missing_colbert_raises_index_error(monkeypatch, tmp_path):
    def fake_import(name, *args, **kwargs):
        if name.startswith("colbert"):
            raise ModuleNotFoundError("colbert")
        return importlib.import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    index = ColbertIndex(index_dir=tmp_path, index_name="test-index")

    with pytest.raises(IndexError) as excinfo:
        index.build_index([("c1", "text")])

    assert "pip install colbert-ai" in str(excinfo.value)
