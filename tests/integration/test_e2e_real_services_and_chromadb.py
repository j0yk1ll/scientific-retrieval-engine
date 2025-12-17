"""End-to-end test with real Docker services (Postgres + GROBID) and ChromaDB.

This version adds strong PDF + GROBID preflight checks to avoid false attribution:
- Verifies fixture PDFs are real PDFs (magic bytes, size, EOF marker heuristic).
- Computes sha256 + logs size.
- Sends the fixture PDFs to Grobid via requests in a way that mirrors `curl -F input=@...`.
- Fails with actionable diagnostics if Grobid parsing fails.

If Grobid preflight succeeds but engine ingestion fails, the defect is almost certainly
in the engine's Grobid upload logic (e.g., consumed stream/not rewound, truncation, etc.).
"""

from __future__ import annotations

import hashlib
import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import pytest
import requests

from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine
from retrieval.storage.db import get_connection
from retrieval.storage.migrations import run_migrations


# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
PDF_DIR = FIXTURES_DIR / "pdf"
PAPER1_PDF = PDF_DIR / "paper1.pdf"
PAPER2_PDF = PDF_DIR / "paper2.pdf"

# Default service URLs
DEFAULT_GROBID_URL = "http://localhost:8070"
DEFAULT_DB_DSN = "postgresql://retrieval:retrieval@localhost:5432/retrieval"


@dataclass(frozen=True)
class PdfDiagnostics:
    path: Path
    size_bytes: int
    sha256: str
    starts_with_pdf: bool
    tail_has_eof: bool
    head_hex: str
    tail_hex: str


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _pdf_diagnostics(path: Path) -> PdfDiagnostics:
    data = path.read_bytes()
    size = len(data)
    starts_with_pdf = data[:5] == b"%PDF-"
    # Heuristic: many valid PDFs include %%EOF near the end; absence can hint truncation.
    # Not definitive, but very useful signal.
    tail_window = data[-2048:] if size >= 2048 else data
    tail_has_eof = b"%%EOF" in tail_window
    head_hex = data[:32].hex()
    tail_hex = data[-32:].hex() if size >= 32 else data.hex()
    return PdfDiagnostics(
        path=path,
        size_bytes=size,
        sha256=_sha256_bytes(data),
        starts_with_pdf=starts_with_pdf,
        tail_has_eof=tail_has_eof,
        head_hex=head_hex,
        tail_hex=tail_hex,
    )


def _chromadb_available() -> bool:
    """Check if ChromaDB server is reachable."""
    try:
        response = requests.get("http://localhost:8000/api/v2/heartbeat", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _grobid_available(base_url: str) -> bool:
    """Check if GROBID service is reachable."""
    try:
        response = requests.get(f"{base_url}/api/isalive", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _postgres_available(dsn: str) -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        conn = get_connection(dsn)
        conn.close()
        return True
    except Exception:
        return False


def _get_config() -> tuple[str, str]:
    """Get DSN and GROBID URL from environment or defaults."""
    dsn = os.getenv("RETRIEVAL_DB_DSN", DEFAULT_DB_DSN)
    grobid_url = os.getenv("RETRIEVAL_GROBID_URL", DEFAULT_GROBID_URL)
    return dsn, grobid_url


def _services_available() -> bool:
    """Check if all required services are available."""
    dsn, grobid_url = _get_config()
    return (
        _chromadb_available()
        and _grobid_available(grobid_url)
        and _postgres_available(dsn)
    )


def _assert_fixture_pdf_ok(path: Path) -> PdfDiagnostics:
    """Validate PDF fixture sanity before running expensive E2E steps."""
    assert path.exists(), f"Fixture PDF not found: {path}"
    diag = _pdf_diagnostics(path)

    # Hard checks: must be a PDF by magic bytes and non-trivial size.
    assert diag.starts_with_pdf, (
        f"{path} does not start with %PDF-. "
        f"head_hex={diag.head_hex} size={diag.size_bytes}"
    )
    # Size floor: adjust if your fixtures can be tiny, but keep something > 10KB.
    assert diag.size_bytes > 10_000, (
        f"{path} is unexpectedly small for a paper PDF ({diag.size_bytes} bytes). "
        f"sha256={diag.sha256}"
    )

    # Soft warning signal: don't fail on missing %%EOF, but note it in assertion messages later.
    return diag


def _grobid_parse_fulltext(base_url: str, pdf_path: Path, timeout_s: float) -> str:
    """Send a PDF to Grobid and return TEI XML as text.

    This uses a requests multipart upload intended to mirror:
      curl -F "input=@file.pdf;type=application/pdf" http://.../api/processFulltextDocument
    """
    pdf_bytes = pdf_path.read_bytes()
    files = {
        # Field name must be "input" for /api/processFulltextDocument
        "input": (pdf_path.name, pdf_bytes, "application/pdf"),
    }
    resp = requests.post(
        f"{base_url}/api/processFulltextDocument",
        files=files,
        timeout=timeout_s,
    )
    # Raise with context, including a snippet to help debug if an HTML error page is returned.
    if resp.status_code != 200:
        snippet = resp.text[:800] if resp.text else "<empty>"
        raise AssertionError(
            f"Grobid returned {resp.status_code} for {pdf_path.name}. "
            f"Response snippet: {snippet}"
        )
    # Grobid returns TEI XML; ensure it's non-empty and looks like XML.
    tei = resp.text or ""
    assert tei.strip(), f"Grobid returned empty body for {pdf_path.name}"
    assert "<TEI" in tei or "<tei" in tei, (
        f"Grobid response for {pdf_path.name} does not look like TEI XML. "
        f"First 400 chars: {tei[:400]}"
    )
    return tei


pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not _services_available(),
        reason="E2E tests require Docker services (Postgres + GROBID + ChromaDB) running",
    ),
]


@pytest.fixture
def clean_database() -> Generator[str, None, None]:
    """Run migrations and clean up test data after the test."""
    dsn, _ = _get_config()

    # Run migrations
    run_migrations(dsn=dsn)

    yield dsn

    # Clean up test data
    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            # Delete chunks first due to foreign key constraints
            cur.execute("DELETE FROM chunks")
            cur.execute("DELETE FROM paper_files")
            cur.execute("DELETE FROM paper_sources")
            cur.execute("DELETE FROM paper_authors")
            cur.execute("DELETE FROM papers")
        conn.commit()


@pytest.fixture
def engine_config(tmp_path: Path, clean_database: str) -> RetrievalConfig:
    """Create a configuration for the E2E test."""
    dsn, grobid_url = _get_config()
    return RetrievalConfig(
        db_dsn=dsn,
        data_dir=tmp_path / "data",
        index_dir=tmp_path / "index",
        chroma_url="http://localhost:8000",
        grobid_url=grobid_url,
        unpaywall_email="e2e-test@example.com",
        request_timeout_s=180.0,  # Grobid can be slow; be generous in integration tests
    )


@pytest.fixture
def engine(engine_config: RetrievalConfig) -> RetrievalEngine:
    """Create a RetrievalEngine instance."""
    return RetrievalEngine(engine_config)


class TestE2ERealServicesAndChromaDB:
    """End-to-end tests with real services."""

    def test_ingest_local_pdfs_build_index_and_search(
        self,
        engine: RetrievalEngine,
        clean_database: str,
    ) -> None:
        """
        Full E2E test:
        0. Preflight: validate fixture PDFs and direct Grobid parsing (curl-equivalent)
        1. Ingest local PDFs with metadata
        2. Parse with GROBID
        3. Chunk the TEI XML
        4. Build ChromaDB index
        5. Search and validate evidence bundle
        """
        # Skip if PDFs don't exist
        if not PAPER1_PDF.exists() or not PAPER2_PDF.exists():
            pytest.skip("Fixture PDFs not found")

        # 0) Preflight: validate fixture PDF bytes and ensure Grobid can parse them directly
        _, grobid_url = _get_config()
        p1_diag = _assert_fixture_pdf_ok(PAPER1_PDF)
        p2_diag = _assert_fixture_pdf_ok(PAPER2_PDF)

        # Direct Grobid call should work. If it does not, fail early with strong diagnostics.
        try:
            _grobid_parse_fulltext(grobid_url, PAPER1_PDF, timeout_s=engine.config.request_timeout_s)
            _grobid_parse_fulltext(grobid_url, PAPER2_PDF, timeout_s=engine.config.request_timeout_s)
        except AssertionError as e:
            raise AssertionError(
                "Grobid preflight failed. This indicates a service/environment/PDF issue before the engine runs.\n"
                f"PAPER1: size={p1_diag.size_bytes} sha256={p1_diag.sha256} "
                f"starts_with_pdf={p1_diag.starts_with_pdf} tail_has_eof={p1_diag.tail_has_eof}\n"
                f"PAPER2: size={p2_diag.size_bytes} sha256={p2_diag.sha256} "
                f"starts_with_pdf={p2_diag.starts_with_pdf} tail_has_eof={p2_diag.tail_has_eof}\n"
                f"Details: {e}"
            ) from e

        # 1. Ingest paper 1 from local PDF
        paper1 = engine.ingest_from_local_pdf(
            PAPER1_PDF,
            title="Introduction to Machine Learning Methods",
            abstract="A comprehensive survey of machine learning approaches.",
            authors=["Alice Smith", "Bob Johnson"],
            source_name="local_pdf",
            source_identifier="paper1.pdf",
        )

        assert paper1.id is not None
        assert paper1.title == "Introduction to Machine Learning Methods"

        # 2. Ingest paper 2 from local PDF
        paper2 = engine.ingest_from_local_pdf(
            PAPER2_PDF,
            title="Deep Learning for Natural Language Processing",
            abstract="Exploring transformer architectures for NLP tasks.",
            authors=["Charlie Brown"],
            source_name="local_pdf",
            source_identifier="paper2.pdf",
        )

        assert paper2.id is not None
        assert paper2.title == "Deep Learning for Natural Language Processing"

        # 3. Verify chunks were created in the database
        with get_connection(clean_database) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chunks WHERE paper_id = %s", (paper1.id,))
                paper1_chunk_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM chunks WHERE paper_id = %s", (paper2.id,))
                paper2_chunk_count = cur.fetchone()[0]

        assert paper1_chunk_count > 0, "Paper 1 should have chunks"
        assert paper2_chunk_count > 0, "Paper 2 should have chunks"

        # 4. Build ChromaDB index
        index_path = engine.rebuild_index()

        assert index_path.exists(), "Index directory should exist"

        # 5. Search for machine learning content
        ml_results = engine.search("machine learning neural networks", top_k=5)

        assert len(ml_results) > 0, "Should find results for machine learning query"

        # Verify search results contain expected content
        result_paper_ids = {r.paper_id for r in ml_results}
        assert paper1.id in result_paper_ids, "Paper 1 should appear in ML search results"

        # 6. Search for NLP content
        nlp_results = engine.search("transformer attention natural language", top_k=5)

        assert len(nlp_results) > 0, "Should find results for NLP query"

        nlp_result_paper_ids = {r.paper_id for r in nlp_results}
        assert paper2.id in nlp_result_paper_ids, "Paper 2 should appear in NLP search results"

        # 7. Test evidence bundle
        bundle = engine.evidence_bundle(
            "machine learning methods optimization",
            top_k=5,
            max_per_paper=2,
        )

        assert bundle.query == "machine learning methods optimization"
        assert len(bundle.papers) > 0, "Evidence bundle should contain papers"

        # Verify bundle structure
        for evidence_paper in bundle.papers:
            assert evidence_paper.paper.id is not None
            assert len(evidence_paper.chunks) > 0
            assert len(evidence_paper.chunks) <= 2, "max_per_paper should be respected"
            for chunk in evidence_paper.chunks:
                assert chunk.content, "Chunk should have content"
                assert chunk.score > 0, "Chunk should have positive score"

    def test_ingest_single_pdf_and_verify_provenance(
        self,
        engine: RetrievalEngine,
        clean_database: str,
    ) -> None:
        """Test that ingestion records proper provenance information."""
        if not PAPER1_PDF.exists():
            pytest.skip("Fixture PDF not found")

        # Preflight sanity for clearer failure messages
        _assert_fixture_pdf_ok(PAPER1_PDF)

        paper = engine.ingest_from_local_pdf(
            PAPER1_PDF,
            title="Provenance Test Paper",
            abstract="Testing source tracking.",
            doi="10.1234/test.doi",
            source_metadata={"origin": "e2e_test"},
        )

        # Verify provenance in database
        with get_connection(clean_database) as conn:
            with conn.cursor() as cur:
                # Check paper_sources
                cur.execute(
                    "SELECT source_name, source_identifier, metadata FROM paper_sources WHERE paper_id = %s",
                    (paper.id,),
                )
                source = cur.fetchone()

                assert source is not None
                assert source[0] == "local_pdf"
                assert PAPER1_PDF.name in source[1]
                assert source[2]["origin"] == "e2e_test"

    def test_rebuild_index_is_idempotent(
        self,
        engine: RetrievalEngine,
        clean_database: str,
    ) -> None:
        """Test that rebuilding the index multiple times works correctly."""
        if not PAPER1_PDF.exists():
            pytest.skip("Fixture PDF not found")

        _assert_fixture_pdf_ok(PAPER1_PDF)

        # Ingest a paper
        engine.ingest_from_local_pdf(
            PAPER1_PDF,
            title="Idempotent Test Paper",
        )

        # Build index twice
        index_path1 = engine.rebuild_index()
        index_path2 = engine.rebuild_index()

        assert index_path1 == index_path2
        assert index_path2.exists()

        # Search should still work
        results = engine.search("machine learning", top_k=3)
        assert len(results) > 0

    def test_empty_query_returns_no_results(
        self,
        engine: RetrievalEngine,
        clean_database: str,
    ) -> None:
        """Test that empty queries are handled gracefully."""
        results = engine.search("", top_k=5)
        assert results == []

        results = engine.search("   ", top_k=5)
        assert results == []

    def test_search_with_min_score_filter(
        self,
        engine: RetrievalEngine,
        clean_database: str,
    ) -> None:
        """Test that min_score filtering works."""
        if not PAPER1_PDF.exists():
            pytest.skip("Fixture PDF not found")

        _assert_fixture_pdf_ok(PAPER1_PDF)

        engine.ingest_from_local_pdf(
            PAPER1_PDF,
            title="Min Score Test Paper",
        )
        engine.rebuild_index()

        # Search with a very high min_score should return fewer or no results
        all_results = engine.search("machine learning", top_k=10)
        high_score_results = engine.search("machine learning", top_k=10, min_score=100.0)

        assert len(high_score_results) <= len(all_results)
