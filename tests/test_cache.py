import json
import os
import re
from pathlib import Path

import pytest

from retrieval.cache import CACHE_VERSION, CachedPaperPipeline, DoiFileCache
from retrieval.chunking.grobid_chunker import GrobidChunker
from retrieval.models import Paper


class DummyEmbedder:
    model_name = "dummy-model"
    normalized = True

    def __init__(self, dim: int = 4) -> None:
        self.dim = dim
        self.dimension = dim

    def embed(self, texts):
        return [[float(i)] * self.dim for i, _ in enumerate(texts)]


class DummyGrobidClient:
    def process_fulltext(self, pdf, consolidate_header=True):
        return "<xml/>"


class DummyMergeService:
    def merge(self, candidates):
        return candidates[0]


class DummySearchService:
    def __init__(self) -> None:
        self.merge_service = DummyMergeService()

    def search_by_doi(self, doi):
        return [Paper(paper_id="pid", title="t", doi=doi)]


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_cache_write_is_atomic_via_replace(monkeypatch, cache_dir: Path):
    cache = DoiFileCache(cache_dir)
    metadata_path = cache._metadata_path("10.0000/abc")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("old")

    calls = []

    def crash_replace(src, dst):
        calls.append((src, dst))
        raise RuntimeError("crash")

    monkeypatch.setattr(os, "replace", crash_replace)

    with pytest.raises(RuntimeError):
        cache.store_metadata(
            "10.0000/abc",
            Paper(
                paper_id="pid",
                title="t",
                doi="d",
                abstract=None,
                year=None,
                venue=None,
                source="test",
            ),
        )

    assert metadata_path.read_text() == "old"
    assert calls, "os.replace should be used for atomic writes"


def test_cache_key_sanitization_rejects_or_normalizes_unsafe_chars(cache_dir: Path):
    cache = DoiFileCache(cache_dir)
    path = cache._doi_dir("10.1234/ABC DEF?%$")
    assert path.parent == cache_dir
    assert re.fullmatch(r"[a-z0-9._-]+", path.name)


def test_metadata_loads_without_manifest(cache_dir: Path):
    cache = DoiFileCache(cache_dir)
    doi = "10.0000/abc"
    paper = Paper(
        paper_id="pid",
        title="t",
        doi=doi,
        abstract=None,
        year=None,
        venue=None,
        source="test",
    )
    cache.store_metadata(doi, paper)

    loaded = cache.load_metadata(doi)

    assert loaded is not None
    assert loaded.doi == doi


def test_cache_version_mismatch_invalidates_or_ignores_old_entries(cache_dir: Path):
    cache_dir.mkdir(parents=True, exist_ok=True)
    version_file = cache_dir / "cache_version"
    version_file.write_text("0")
    old_metadata = cache_dir / "old.json"
    old_metadata.write_text("legacy")

    cache = DoiFileCache(cache_dir)
    metadata = cache.load_metadata("10.0000/abc")

    assert metadata is None
    assert version_file.read_text() == CACHE_VERSION
    assert not old_metadata.exists()


def test_embedding_metadata_is_saved(cache_dir: Path):
    cache = DoiFileCache(cache_dir)
    embedder = DummyEmbedder(dim=3)
    pipeline = CachedPaperPipeline(
        cache=cache,
        search_service=DummySearchService(),
        grobid_client=DummyGrobidClient(),
        embedder=embedder,
    )

    cache.store_metadata(
        "10.0000/abc",
        Paper(
            paper_id="pid",
            title="t",
            doi="10.0000/abc",
            abstract=None,
            year=None,
            venue=None,
            source="test",
        ),
    )
    cache.store_tei("10.0000/abc", "tei")
    cache.store_chunks("10.0000/abc", [])

    artifacts = pipeline.ingest("10.0000/abc", pdf="pdf")
    embeddings_path = cache._embeddings_path("10.0000/abc")
    payload = json.loads(embeddings_path.read_text())

    assert payload["metadata"]["model"] == embedder.model_name
    assert payload["metadata"]["chunker_version"] == GrobidChunker.VERSION
    assert len(payload["embeddings"]) == len(artifacts.embeddings)


def test_embeddings_are_invalidated_when_embedder_changes(cache_dir: Path) -> None:
    cache = DoiFileCache(
        cache_dir,
        chunk_encoding_name="enc",
        chunker_version="chunker-v1",
        embedder_model_name="model-a",
        embedder_dimension=3,
        embedder_normalized=True,
    )
    doi = "10.0000/abc"

    embeddings_path = cache._embeddings_path(doi)
    embeddings_path.parent.mkdir(parents=True, exist_ok=True)
    embeddings_path.write_text(json.dumps({"embeddings": [[0.1, 0.2, 0.3]]}))

    manifest = {
        "cache_version": CACHE_VERSION,
        "chunker_version": "chunker-v1",
        "encoding": "enc",
        "embedder": {"model": "model-a", "dimension": 2, "normalized": True},
    }
    cache._write_manifest(doi, manifest)

    assert cache.load_embeddings(doi) is None
    assert not embeddings_path.exists()


def test_manifest_is_preserved_when_chunks_invalidated(cache_dir: Path) -> None:
    cache = DoiFileCache(cache_dir, chunk_encoding_name="enc", chunker_version="v1")
    doi = "10.0000/retain-manifest"

    manifest = {
        "cache_version": CACHE_VERSION,
        "chunker_version": "v1",
        "encoding": "enc",
    }
    cache._doi_dir(doi).mkdir(parents=True, exist_ok=True)
    cache._write_manifest(doi, manifest)
    cache._chunks_path(doi).write_text("[]")
    cache._embeddings_path(doi).write_text(json.dumps({"embeddings": []}))

    cache.chunk_encoding_name = "other"

    assert cache.load_chunks(doi) is None
    assert cache._manifest_path(doi).exists()
    assert not cache._chunks_path(doi).exists()
    assert not cache._embeddings_path(doi).exists()


def test_embeddings_are_invalidated_when_dimension_mismatch(cache_dir: Path) -> None:
    cache = DoiFileCache(cache_dir, embedder_dimension=3)
    doi = "10.0000/dimension"

    manifest = {
        "cache_version": CACHE_VERSION,
        "chunker_version": "v1",
        "encoding": None,
        "embedder": {"model": "m", "dimension": 3, "normalized": False},
    }

    cache._doi_dir(doi).mkdir(parents=True, exist_ok=True)
    cache._write_manifest(doi, manifest)
    cache._embeddings_path(doi).write_text(
        json.dumps({"embeddings": [[0.1, 0.2]]})
    )

    assert cache.load_embeddings(doi) is None
    assert not cache._embeddings_path(doi).exists()

