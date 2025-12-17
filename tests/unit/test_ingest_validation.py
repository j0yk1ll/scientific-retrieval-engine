from pathlib import Path

import pytest

from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine


def _make_config(tmp_path: Path) -> RetrievalConfig:
    return RetrievalConfig(
        db_dsn="postgresql://localhost/placeholder",
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "index",
        chroma_url="http://localhost:8000",
        grobid_url="http://example.com",
        unpaywall_email="tester@example.com",
    )


def test_ingest_from_metadata_requires_title(tmp_path: Path) -> None:
    engine = RetrievalEngine(_make_config(tmp_path))

    with pytest.raises(ValueError):
        engine.ingest_from_metadata(title="   ")


def test_ingest_from_doi_requires_identifier(tmp_path: Path) -> None:
    engine = RetrievalEngine(_make_config(tmp_path))

    with pytest.raises(ValueError):
        engine.ingest_from_doi(doi="")


def test_ingest_from_openalex_requires_identifier(tmp_path: Path) -> None:
    engine = RetrievalEngine(_make_config(tmp_path))

    with pytest.raises(ValueError):
        engine.ingest_from_openalex(openalex_work_id="  ")
