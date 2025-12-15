import json
import os
from pathlib import Path
from typing import Iterable

import pytest
import responses

from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine
from retrieval.exceptions import ParseError
from retrieval.storage.db import get_connection
from scripts.migrate import run_migrations


def _load_openalex_fixture() -> dict:
    fixture_path = Path(__file__).parent.parent / "fixtures" / "http" / "openalex_work.json"
    return json.loads(fixture_path.read_text())


def _sample_pdf_bytes() -> bytes:
    pdf_path = Path(__file__).parent.parent / "fixtures" / "tei" / "sample.pdf"
    return pdf_path.read_bytes()


def _sample_tei_xml() -> str:
    xml_path = Path(__file__).parent.parent / "fixtures" / "tei" / "sample.tei.xml"
    return xml_path.read_text()


def _require_dsn() -> str:
    dsn = os.getenv("RETRIEVAL_DB_DSN")
    if not dsn:
        pytest.skip("RETRIEVAL_DB_DSN not set")
    return dsn


def _make_config(tmp_path: Path, dsn: str) -> RetrievalConfig:
    return RetrievalConfig(
        db_dsn=dsn,
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "index",
        grobid_url="http://grobid.test",
        unpaywall_email="tester@example.com",
        request_timeout_s=1.0,
    )


@pytest.fixture
def migrated_db() -> Iterable[str]:
    dsn = _require_dsn()
    run_migrations(dsn=dsn)
    yield dsn


@pytest.mark.integration
@responses.activate
def test_ingest_from_doi_with_mocked_dependencies(tmp_path: Path, migrated_db: str) -> None:
    doi = "10.5555/example.doi"
    pdf_url = "https://example.test/paper.pdf"
    tei_xml = _sample_tei_xml()

    openalex_payload = _load_openalex_fixture()
    responses.add(
        responses.GET,
        "https://api.openalex.org/works",
        json={"results": [openalex_payload], "meta": {"next_cursor": None}},
        status=200,
    )

    responses.add(
        responses.GET,
        f"https://api.unpaywall.org/v2/{doi}",
        json={
            "doi": doi,
            "title": "Example OpenAlex Work",
            "best_oa_location": {"url": pdf_url, "url_for_pdf": pdf_url, "is_best": True},
            "oa_locations": [],
        },
        status=200,
    )

    responses.add(
        responses.GET,
        pdf_url,
        body=_sample_pdf_bytes(),
        status=200,
        headers={"Content-Type": "application/pdf"},
    )

    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body=tei_xml,
        status=200,
        content_type="text/xml",
    )

    config = _make_config(tmp_path, migrated_db)
    engine = RetrievalEngine(config)

    paper = engine.ingest_from_doi(doi)

    with get_connection(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_name, source_identifier FROM paper_sources WHERE paper_id = %s",
                (paper.id,),
            )
            sources = cur.fetchall()

            cur.execute(
                "SELECT file_type, location FROM paper_files WHERE paper_id = %s",
                (paper.id,),
            )
            files = cur.fetchall()

            cur.execute("SELECT count(*) FROM chunks WHERE paper_id = %s", (paper.id,))
            chunk_count = cur.fetchone()[0]

    assert ("doi", doi) in sources
    assert any(row[0] == "pdf" for row in files)
    assert any(row[0] == "tei" and row[1].endswith(".tei.xml") for row in files)
    assert chunk_count > 0


@pytest.mark.integration
@responses.activate
def test_parse_failure_records_status(tmp_path: Path, migrated_db: str) -> None:
    doi = "10.0000/parse.fail"
    pdf_url = "https://example.test/failing.pdf"

    responses.add(
        responses.GET,
        "https://api.openalex.org/works",
        json={"results": [], "meta": {"next_cursor": None}},
        status=200,
    )

    responses.add(
        responses.GET,
        f"https://api.unpaywall.org/v2/{doi}",
        json={
            "doi": doi,
            "title": "Parse Failure Example",
            "best_oa_location": {"url": pdf_url, "url_for_pdf": pdf_url, "is_best": True},
            "oa_locations": [],
        },
        status=200,
    )

    responses.add(
        responses.GET,
        pdf_url,
        body=_sample_pdf_bytes(),
        status=200,
        headers={"Content-Type": "application/pdf"},
    )

    responses.add(
        responses.POST,
        "http://grobid.test/api/processFulltextDocument",
        body="",
        status=500,
    )

    config = _make_config(tmp_path, migrated_db)
    engine = RetrievalEngine(config)

    with pytest.raises(ParseError):
        engine.ingest_from_doi(doi)

    with get_connection(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_type, location FROM paper_files WHERE file_type = 'tei' ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()

    assert row is not None
    assert row[1] == "parse_failed"
