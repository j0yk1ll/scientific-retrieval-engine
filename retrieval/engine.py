"""Primary entrypoint for the retrieval system."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, List, Sequence

import requests

from retrieval.acquisition.downloader import PDFDownloader
from retrieval.acquisition.preprints.arxiv import ArxivClient
from retrieval.acquisition.preprints.chemrxiv import ChemRxivClient
from retrieval.acquisition.preprints.medrxiv import MedRxivClient
from retrieval.acquisition.unpaywall import FullTextCandidate, UnpaywallClient, resolve_full_text
from retrieval.config import RetrievalConfig
from retrieval.discovery.openalex import OpenAlexClient, OpenAlexWork
from retrieval.exceptions import AcquisitionError, ConfigError, ParseError
from retrieval.index.colbert import ColbertIndex
from retrieval.parsing.grobid_client import GrobidClient
from retrieval.parsing.tei_chunker import TEIChunk, TEIChunker
from retrieval.retrieval.postprocess import postprocess_results
from retrieval.retrieval.types import ChunkSearchResult, EvidenceBundle
from retrieval.storage.dao import (
    get_all_chunks,
    get_chunks_by_ids,
    get_papers_by_ids,
    insert_chunks,
    insert_paper_source,
    replace_authors,
    upsert_paper,
    upsert_paper_files,
)
from retrieval.storage.db import get_connection
from retrieval.storage.files import (
    atomic_write_bytes,
    atomic_write_text,
    pdf_path,
    sha256_bytes,
    tei_path,
)
from retrieval.storage.models import Chunk, Paper, PaperAuthor, PaperFile, PaperSource


class RetrievalEngine:
    """Coordinates acquisition, parsing, indexing, and retrieval."""

    index_name = "papers"

    def __init__(self, config: RetrievalConfig) -> None:
        self.config = config
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for path in (self.config.data_dir, self.config.index_dir):
            if path.exists() and not path.is_dir():
                raise ConfigError(f"Configured path is not a directory: {path}")
            path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public ingestion entrypoints
    # ------------------------------------------------------------------
    def ingest_from_metadata(
        self,
        *,
        title: str,
        abstract: str | None = None,
        doi: str | None = None,
        published_at: date | None = None,
        authors: Sequence[str] | None = None,
        source_name: str = "metadata",
        source_identifier: str | None = None,
        source_metadata: dict | None = None,
    ) -> Paper:
        """Ingest a paper when metadata (including *title*) is already known."""

        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title is required for ingestion")

        conn = get_connection(self.config.db_dsn)
        paper: Paper | None = None
        try:
            paper = self._persist_paper_metadata(
                conn,
                title=normalized_title,
                abstract=abstract,
                doi=doi,
                published_at=published_at,
                authors=authors,
            )
            self._record_source(
                conn,
                paper_id=paper.id,
                source_name=source_name,
                source_identifier=source_identifier,
                metadata=source_metadata,
            )

            candidate = self._resolve_full_text(doi=doi, title=normalized_title)
            if candidate is None:
                raise AcquisitionError("Unable to resolve a full-text PDF for ingestion")

            _, pdf_disk_path = self._download_and_store_pdf(conn, paper_id=paper.id, candidate=candidate)

            _tei_record, tei_xml = self._parse_and_store(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_disk_path
            )

            self._chunk_and_store(conn, paper_id=paper.id, tei_xml=tei_xml)

            conn.commit()
            return paper
        except ParseError:
            self._record_parse_status(conn, paper_id=paper.id, status="parse_failed")
            conn.commit()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ingest_from_doi(self, doi: str) -> Paper:
        """Resolve metadata by DOI then ingest using Unpaywall/preprint flows."""

        normalized_doi = (doi or "").strip()
        if not normalized_doi:
            raise ValueError("A DOI must be provided for DOI ingestion")

        metadata = self._metadata_from_openalex(doi=normalized_doi)
        title = metadata.get("title")

        if not title:
            try:
                record = self._unpaywall_client().get_record(normalized_doi)
                title = record.title or ""
            except requests.RequestException:
                title = ""

        if not title:
            raise AcquisitionError("Unable to resolve title for DOI ingestion")

        return self.ingest_from_metadata(
            title=title,
            abstract=metadata.get("abstract"),
            doi=normalized_doi,
            published_at=metadata.get("published_at"),
            authors=metadata.get("authors"),
            source_name="doi",
            source_identifier=normalized_doi,
            source_metadata=metadata or None,
        )

    def ingest_from_openalex(self, openalex_work_id: str) -> Paper:
        """Fetch an OpenAlex work then ingest using the resolved metadata."""

        normalized_id = (openalex_work_id or "").strip()
        if not normalized_id:
            raise ValueError("An OpenAlex work identifier is required")

        client = self._openalex_client()
        work = client.get_work(normalized_id)
        metadata = self._metadata_from_work(work)

        return self.ingest_from_metadata(
            title=metadata["title"],
            abstract=metadata.get("abstract"),
            doi=metadata.get("doi"),
            published_at=metadata.get("published_at"),
            authors=metadata.get("authors"),
            source_name="openalex",
            source_identifier=work.openalex_id,
            source_metadata={"venue": work.venue},
        )

    def ingest_from_local_pdf(
        self,
        local_pdf_path: Path | str,
        *,
        title: str,
        abstract: str | None = None,
        doi: str | None = None,
        published_at: date | None = None,
        authors: Sequence[str] | None = None,
        source_name: str = "local_pdf",
        source_identifier: str | None = None,
        source_metadata: dict | None = None,
    ) -> Paper:
        """Ingest a paper from a local PDF file with provided metadata.

        This method bypasses the full-text resolution step and directly uses
        the provided PDF file for parsing and chunking.
        """
        pdf_file = Path(local_pdf_path)
        if not pdf_file.is_file():
            raise AcquisitionError(f"Local PDF file not found: {pdf_file}")

        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("title is required for ingestion")

        conn = get_connection(self.config.db_dsn)
        paper: Paper | None = None
        try:
            paper = self._persist_paper_metadata(
                conn,
                title=normalized_title,
                abstract=abstract,
                doi=doi,
                published_at=published_at,
                authors=authors,
            )
            self._record_source(
                conn,
                paper_id=paper.id,
                source_name=source_name,
                source_identifier=source_identifier or str(pdf_file),
                metadata=source_metadata,
            )

            # Copy PDF to data directory
            pdf_disk_path = self._store_local_pdf(conn, paper_id=paper.id, source_path=pdf_file)

            _tei_record, tei_xml = self._parse_and_store(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_disk_path
            )

            self._chunk_and_store(conn, paper_id=paper.id, tei_xml=tei_xml)

            conn.commit()
            return paper
        except ParseError:
            if paper is not None:
                self._record_parse_status(conn, paper_id=paper.id, status="parse_failed")
                conn.commit()
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Individual pipeline stages
    # ------------------------------------------------------------------
    def discover(self, query: str) -> Sequence[str]:
        """Discover candidate papers using metadata sources."""

        raise NotImplementedError

    def acquire_full_text(self, work_identifier: str) -> Path:
        """Download full-text content for a work and return the saved path."""

        raise NotImplementedError

    def parse_document(self, pdf_path: Path) -> str:
        """Convert a PDF to TEI XML using GROBID."""

        client = self._grobid_client()
        return client.process_fulltext(pdf_path)

    def chunk_document(self, tei_xml: str) -> List[str]:
        """Chunk TEI XML into deterministic passages ready for indexing."""

        chunker = self._tei_chunker()
        return [chunk.text for chunk in chunker.chunk(tei_xml)]

    def index_chunks(self, chunks: Iterable[str]) -> None:
        """Index chunks using ColBERT."""

        raise NotImplementedError

    def rebuild_index(self) -> Path:
        """Export chunks to TSV and rebuild the ColBERT index."""

        conn = get_connection(self.config.db_dsn)
        try:
            chunks = get_all_chunks(conn)
        finally:
            conn.close()

        rows = [
            (str(chunk.id), chunk.content) for chunk in chunks if chunk.id is not None
        ]
        return self._colbert_index().build_index(rows)

    def search(
        self,
        query: str,
        top_k: int = 10,
        *,
        min_score: float | None = None,
        max_per_paper: int = 2,
    ) -> Sequence[ChunkSearchResult]:
        """Search the ColBERT index and return ranked chunk results."""

        normalized_query = query.strip()
        if not normalized_query:
            return []

        ranking = self._colbert_index().search(normalized_query, top_k=top_k)

        chunk_ids: list[int] = []
        scores: dict[int, float] = {}
        for chunk_id, score in ranking:
            try:
                parsed_id = int(chunk_id)
            except (TypeError, ValueError):
                continue
            if parsed_id not in scores:
                chunk_ids.append(parsed_id)
            scores[parsed_id] = max(scores.get(parsed_id, float("-inf")), score)

        conn = get_connection(self.config.db_dsn)
        try:
            chunk_models = get_chunks_by_ids(conn, chunk_ids)
        finally:
            conn.close()

        chunk_map = {chunk.id: chunk for chunk in chunk_models if chunk.id is not None}
        results: list[ChunkSearchResult] = []
        for chunk_id in chunk_ids:
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
            results.append(
                ChunkSearchResult(
                    chunk_id=chunk_id,
                    paper_id=chunk.paper_id,
                    chunk_order=chunk.chunk_order,
                    content=chunk.content,
                    score=scores.get(chunk_id, 0.0),
                )
            )

        return postprocess_results(
            results, min_score=min_score, max_per_paper=max_per_paper
        )

    def evidence_bundle(
        self,
        query: str,
        top_k: int = 10,
        *,
        min_score: float | None = None,
        max_per_paper: int = 2,
    ) -> EvidenceBundle:
        """Execute a search and return grouped evidence by paper."""

        chunk_results = self.search(
            query,
            top_k=top_k,
            min_score=min_score,
            max_per_paper=max_per_paper,
        )

        paper_ids = {result.paper_id for result in chunk_results}
        conn = get_connection(self.config.db_dsn)
        try:
            papers = get_papers_by_ids(conn, list(paper_ids))
        finally:
            conn.close()

        paper_map = {paper.id: paper for paper in papers if paper.id is not None}
        return EvidenceBundle.from_chunks(query, paper_map, chunk_results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _persist_paper_metadata(
        self,
        conn,
        *,
        title: str,
        abstract: str | None,
        doi: str | None,
        published_at: date | None,
        authors: Sequence[str] | None,
    ) -> Paper:
        paper = Paper(title=title, abstract=abstract, doi=doi, published_at=published_at)
        persisted = upsert_paper(conn, paper)

        if authors:
            author_models = [
                PaperAuthor(
                    paper_id=persisted.id,
                    author_name=name,
                    author_order=idx + 1,
                )
                for idx, name in enumerate(authors)
            ]
            replace_authors(conn, persisted.id, author_models)

        return persisted

    def _record_source(
        self,
        conn,
        *,
        paper_id: int,
        source_name: str,
        source_identifier: str | None,
        metadata: dict | None,
    ) -> PaperSource:
        source = PaperSource(
            paper_id=paper_id,
            source_name=source_name,
            source_identifier=source_identifier,
            metadata=metadata,
        )
        return insert_paper_source(conn, source)

    def _resolve_full_text(self, *, doi: str | None, title: str) -> FullTextCandidate | None:
        unpaywall = self._unpaywall_client()
        matcher_clients = self._preprint_clients()
        return resolve_full_text(
            doi=doi or "",
            title=title,
            unpaywall_client=unpaywall,
            preprint_clients=matcher_clients,
        )

    def _download_and_store_pdf(
        self, conn, *, paper_id: int, candidate: FullTextCandidate
    ) -> tuple[PaperFile, Path]:
        downloader = self._pdf_downloader()
        pdf_url = candidate.pdf_url or candidate.url
        if not pdf_url:
            raise AcquisitionError("Resolved full text is missing a PDF URL")

        downloaded = downloader.download(pdf_url)
        path = pdf_path(self.config.data_dir, str(paper_id))
        atomic_write_bytes(path, downloaded.content)
        checksum = sha256_bytes(downloaded.content)

        files = [
            PaperFile(
                paper_id=paper_id,
                file_type="pdf",
                location=str(path),
                checksum=checksum,
            )
        ]
        persisted = upsert_paper_files(conn, paper_id, files)[0]
        return persisted, path

    def _store_local_pdf(self, conn, *, paper_id: int, source_path: Path) -> Path:
        """Copy a local PDF to the data directory and record it."""
        pdf_content = source_path.read_bytes()
        path = pdf_path(self.config.data_dir, str(paper_id))
        atomic_write_bytes(path, pdf_content)
        checksum = sha256_bytes(pdf_content)

        files = [
            PaperFile(
                paper_id=paper_id,
                file_type="pdf",
                location=str(path),
                checksum=checksum,
            )
        ]
        upsert_paper_files(conn, paper_id, files)
        return path

    def _parse_and_store(self, conn, *, paper_id: int, pdf_path_on_disk: Path) -> tuple[PaperFile, str]:
        tei_xml = self.parse_document(pdf_path_on_disk)
        path = tei_path(self.config.data_dir, str(paper_id))
        atomic_write_text(path, tei_xml)
        checksum = sha256_bytes(tei_xml.encode("utf-8"))

        files = [
            PaperFile(
                paper_id=paper_id,
                file_type="tei",
                location=str(path),
                checksum=checksum,
            )
        ]
        persisted = upsert_paper_files(conn, paper_id, files)[0]
        return persisted, tei_xml

    def _record_parse_status(self, conn, *, paper_id: int, status: str) -> None:
        failure_file = PaperFile(
            paper_id=paper_id,
            file_type="tei",
            location=status,
            checksum=None,
        )
        upsert_paper_files(conn, paper_id, [failure_file])

    def _chunk_and_store(self, conn, *, paper_id: int, tei_xml: str) -> list[Chunk]:
        chunker = self._tei_chunker()
        tei_chunks: list[TEIChunk] = chunker.chunk(tei_xml)
        chunk_models = [
            Chunk(paper_id=paper_id, chunk_order=index, content=chunk.text)
            for index, chunk in enumerate(tei_chunks)
        ]
        return insert_chunks(conn, chunk_models)

    def _metadata_from_openalex(self, *, doi: str) -> dict:
        client = self._openalex_client()
        try:
            works, _ = client.search_works(query="", filters={"doi": doi})
        except requests.RequestException:
            return {}

        if not works:
            return {}

        work = works[0]
        return self._metadata_from_work(work)

    def _metadata_from_work(self, work: OpenAlexWork) -> dict:
        published_at = date(work.year, 1, 1) if work.year else None
        return {
            "title": work.title or "",
            "abstract": work.abstract,
            "doi": work.doi,
            "published_at": published_at,
            "authors": work.authors or None,
        }

    def _openalex_client(self) -> OpenAlexClient:
        return OpenAlexClient(timeout=self.config.request_timeout_s)

    def _unpaywall_client(self) -> UnpaywallClient:
        return UnpaywallClient(email=self.config.unpaywall_email, timeout=self.config.request_timeout_s)

    def _preprint_clients(self) -> list:
        return [
            ArxivClient(timeout=self.config.request_timeout_s),
            MedRxivClient(timeout=self.config.request_timeout_s),
            ChemRxivClient(timeout=self.config.request_timeout_s),
        ]

    def _pdf_downloader(self) -> PDFDownloader:
        return PDFDownloader(timeout=self.config.request_timeout_s)

    def _grobid_client(self) -> GrobidClient:
        return GrobidClient(self.config.grobid_url, timeout=self.config.request_timeout_s)

    def _tei_chunker(self) -> TEIChunker:
        return TEIChunker()

    def _colbert_index(self) -> ColbertIndex:
        return ColbertIndex(index_dir=self.config.index_dir, index_name=self.index_name)
