from pathlib import Path

from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine


def test_config_and_engine_instantiation(tmp_path: Path) -> None:
    config = RetrievalConfig(
        db_dsn="postgresql://user:pass@localhost:5432/db",
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "index",
        grobid_url="http://localhost:8070",
        unpaywall_email="test@example.com",
        request_timeout_s=15.0,
    )

    engine = RetrievalEngine(config)

    assert config.data_dir.exists()
    assert config.index_dir.exists()

    for method_name in (
        "discover",
        "acquire_full_text",
        "parse_document",
        "chunk_document",
        "index_chunks",
        "search",
    ):
        assert hasattr(engine, method_name)
