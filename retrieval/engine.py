"""Primary entrypoint for the retrieval system."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urlparse
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
from retrieval.index import ChromaIndex
from retrieval.parsing.citations import extract_citations
from retrieval.parsing.grobid_client import GrobidClient
from retrieval.parsing.tei_chunker import TEIChunk, TEIChunker
from retrieval.parsing.tei_header import extract_tei_metadata, TEIMetadata
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
)
from retrieval.storage.db import get_connection
from retrieval.storage.files import (
    atomic_write_bytes,
    pdf_path,
)
from retrieval.storage.models import Chunk, Paper, PaperAuthor, PaperSource


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
        pdf_path_on_disk: Path | None = None
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

            pdf_disk_path = self._download_and_store_pdf(
                conn, paper_id=paper.id, candidate=candidate
            )
            pdf_path_on_disk = pdf_disk_path

            tei_xml = self.parse_document(pdf_disk_path)

            # Update paper metadata with values extracted from GROBID TEI output
            paper = self._update_paper_from_tei(
                conn, paper=paper, tei_xml=tei_xml, override_existing=False
            )

            chunks = self._chunk_and_store(conn, paper_id=paper.id, paper_uuid=paper.paper_id, tei_xml=tei_xml)
            self._index_chunks(chunks)

            self._cleanup_downloaded_pdf(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
            )

            conn.commit()
            return paper
        except ParseError:
            if paper is not None:
                self._cleanup_downloaded_pdf(
                    conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
                )
                conn.rollback()
            raise
        except Exception:
            self._cleanup_downloaded_pdf(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
            )
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
        pdf_path_on_disk: Path | None = None
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
            pdf_disk_path = self._store_local_pdf(
                conn, paper_id=paper.id, source_path=pdf_file
            )
            pdf_path_on_disk = pdf_disk_path

            tei_xml = self.parse_document(pdf_disk_path)

            # Update paper metadata with values extracted from GROBID TEI output
            paper = self._update_paper_from_tei(
                conn, paper=paper, tei_xml=tei_xml, override_existing=False
            )

            chunks = self._chunk_and_store(conn, paper_id=paper.id, paper_uuid=paper.paper_id, tei_xml=tei_xml)
            self._index_chunks(chunks)

            self._cleanup_downloaded_pdf(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
            )

            conn.commit()
            return paper
        except ParseError:
            if paper is not None:
                self._cleanup_downloaded_pdf(
                    conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
                )
                conn.rollback()
            raise
        except Exception:
            self._cleanup_downloaded_pdf(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
            )
            conn.rollback()
            raise
        finally:
            conn.close()

    def ingest_from_url(
        self,
        pdf_url: str,
        *,
        title: str | None = None,
        abstract: str | None = None,
        doi: str | None = None,
        published_at: date | None = None,
        authors: Sequence[str] | None = None,
        source_metadata: dict | None = None,
    ) -> Paper:
        """Ingest a paper directly from a PDF URL.

        The caller may optionally provide metadata. If ``title`` is not given, a
        best-effort title will be derived from the URL path.
        """
        import re

        normalized_url = (pdf_url or "").strip()
        if not normalized_url:
            raise ValueError("A PDF URL must be provided for ingestion")

        resolved_title = (title or "").strip()
        if not resolved_title:
            parsed = urlparse(normalized_url)
            fallback_title = Path(parsed.path).stem
            resolved_title = fallback_title or normalized_url

        # Extract arXiv ID from URL if present
        external_source: str | None = None
        external_id: str | None = None
        arxiv_match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d+)', normalized_url, re.IGNORECASE)
        if arxiv_match:
            external_source = "arxiv"
            external_id = arxiv_match.group(1)

        conn = get_connection(self.config.db_dsn)
        paper: Paper | None = None
        pdf_path_on_disk: Path | None = None
        try:
            paper = self._persist_paper_metadata(
                conn,
                title=resolved_title,
                abstract=abstract,
                doi=doi,
                published_at=published_at,
                authors=authors,
                external_source=external_source,
                external_id=external_id,
            )
            self._record_source(
                conn,
                paper_id=paper.id,
                source_name="url",
                source_identifier=normalized_url,
                metadata={"url": normalized_url, **(source_metadata or {})},
            )

            candidate = FullTextCandidate(
                source="url",
                url=normalized_url,
                pdf_url=normalized_url,
                metadata=source_metadata,
            )

            pdf_disk_path = self._download_and_store_pdf(
                conn, paper_id=paper.id, candidate=candidate
            )
            pdf_path_on_disk = pdf_disk_path

            tei_xml = self.parse_document(pdf_disk_path)

            # Update paper metadata with values extracted from GROBID TEI output
            paper = self._update_paper_from_tei(
                conn, paper=paper, tei_xml=tei_xml, override_existing=False
            )

            chunks = self._chunk_and_store(conn, paper_id=paper.id, paper_uuid=paper.paper_id, tei_xml=tei_xml)
            self._index_chunks(chunks)

            self._cleanup_downloaded_pdf(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
            )

            conn.commit()
            return paper
        except ParseError:
            if paper is not None:
                self._cleanup_downloaded_pdf(
                    conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
                )
                conn.rollback()
            raise
        except Exception:
            self._cleanup_downloaded_pdf(
                conn, paper_id=paper.id, pdf_path_on_disk=pdf_path_on_disk
            )
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
        """Index chunks using ChromaDB."""

        raise NotImplementedError

    def rebuild_index(self) -> Path:
        """Export chunks and rebuild the ChromaDB collection."""

        conn = get_connection(self.config.db_dsn)
        try:
            chunks = get_all_chunks(conn)
        finally:
            conn.close()

        rows = [
            (str(chunk.id), chunk.content) for chunk in chunks if chunk.id is not None
        ]
        return self._chroma_index().build_index(rows)

    def search(
        self,
        query: str,
        top_k: int = 10,
        *,
        min_score: float | None = None,
        max_per_paper: int = 2,
    ) -> Sequence[ChunkSearchResult]:
        """Search the ChromaDB index and return ranked chunk results."""

        normalized_query = query.strip()
        if not normalized_query:
            return []

        ranking = self._chroma_index().search(normalized_query, top_k=top_k)

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
        for db_id in chunk_ids:
            chunk = chunk_map.get(db_id)
            if chunk is None:
                continue
            results.append(
                ChunkSearchResult(
                    chunk_id=chunk.chunk_id,
                    db_id=db_id,
                    paper_id=chunk.paper_id,
                    paper_uuid=chunk.paper_uuid,
                    kind=chunk.kind,
                    position=chunk.position,
                    section_title=chunk.section_title,
                    order_in_section=chunk.order_in_section,
                    content=chunk.content,
                    score=scores.get(db_id, 0.0),
                    citations=tuple(chunk.citations or self._extract_citations(chunk.content)),
                    language=chunk.language,
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
        external_source: str | None = None,
        external_id: str | None = None,
        provenance_source: str = "ingestion",
    ) -> Paper:
        from retrieval.storage.models import generate_paper_uuid
        from datetime import datetime, timezone
        
        paper_uuid = generate_paper_uuid()
        paper = Paper(
            paper_id=paper_uuid,
            title=title,
            abstract=abstract,
            doi=doi,
            published_at=published_at,
            external_source=external_source,
            external_id=external_id,
            provenance_source=provenance_source,
            parser_name="grobid",
            parser_version="0.8.0",  # TODO: Get from config or service
            ingested_at=datetime.now(timezone.utc),
        )
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

    def _update_paper_from_tei(
        self,
        conn,
        *,
        paper: Paper,
        tei_xml: str,
        override_existing: bool = False,
    ) -> Paper:
        """Update paper metadata using values extracted from GROBID TEI output.
        
        This method extracts title, abstract, authors, keywords, and DOI from the
        parsed TEI document and updates the paper record. By default, it only fills
        in missing values (override_existing=False). When override_existing is True,
        it replaces existing values with those from the TEI.
        
        Args:
            conn: Database connection.
            paper: The paper model to update.
            tei_xml: GROBID-generated TEI XML content.
            override_existing: If True, replace existing metadata with TEI values.
            
        Returns:
            The updated Paper model.
        """
        tei_meta = extract_tei_metadata(tei_xml)
        
        updated_title = paper.title
        updated_abstract = paper.abstract
        updated_doi = paper.doi
        updated_keywords = paper.keywords
        
        # Update title if missing or if override is enabled
        if tei_meta.title:
            if override_existing or not paper.title or self._is_placeholder_title(paper.title):
                updated_title = tei_meta.title
        
        # Update abstract if missing or if override is enabled
        if tei_meta.abstract:
            if override_existing or not paper.abstract:
                updated_abstract = tei_meta.abstract
        
        # Update DOI if missing or if override is enabled
        if tei_meta.doi:
            if override_existing or not paper.doi:
                updated_doi = tei_meta.doi
        
        # Update keywords if missing or if override is enabled
        if tei_meta.keywords:
            if override_existing or not paper.keywords:
                updated_keywords = tei_meta.keywords
        
        # Create updated paper model
        updated_paper = Paper(
            id=paper.id,
            paper_id=paper.paper_id,
            title=updated_title,
            abstract=updated_abstract,
            doi=updated_doi,
            published_at=paper.published_at,
            external_source=paper.external_source,
            external_id=paper.external_id,
            venue_name=paper.venue_name,
            venue_type=paper.venue_type,
            venue_publisher=paper.venue_publisher,
            keywords=updated_keywords,
            content_hash=paper.content_hash,
            pdf_sha256=paper.pdf_sha256,
            provenance_source=paper.provenance_source,
            parser_name=paper.parser_name,
            parser_version=paper.parser_version,
            parser_warnings=paper.parser_warnings,
            ingested_at=paper.ingested_at,
            created_at=paper.created_at,
            updated_at=paper.updated_at,
        )
        
        # Persist updated paper
        persisted = upsert_paper(conn, updated_paper)
        
        # Update authors if we have new author data and either override is enabled or no existing authors
        if tei_meta.authors:
            existing_authors = self._get_paper_authors(conn, persisted.id)
            if override_existing or not existing_authors:
                author_models = [
                    PaperAuthor(
                        paper_id=persisted.id,
                        author_name=author.name,
                        author_order=idx + 1,
                        orcid=author.orcid,
                        affiliations=author.affiliations if author.affiliations else None,
                    )
                    for idx, author in enumerate(tei_meta.authors)
                ]
                replace_authors(conn, persisted.id, author_models)
        
        return persisted

    def _is_placeholder_title(self, title: str) -> bool:
        """Check if a title appears to be a placeholder (e.g., URL-derived filename)."""
        import re
        # Match patterns like "2512", "2512.12345", pure numbers, or very short non-word titles
        if not title:
            return True
        # Check for arXiv-style IDs (e.g., "2512", "2512.12345")
        if re.match(r'^\d{4}(\.\d+)?$', title):
            return True
        # Check for pure numbers
        if title.isdigit():
            return True
        # Check for very short titles (less than 3 characters)
        if len(title) < 3:
            return True
        return False

    def _get_paper_authors(self, conn, paper_id: int) -> list[PaperAuthor]:
        """Get authors for a paper."""
        from retrieval.storage.dao import get_paper_authors
        return list(get_paper_authors(conn, paper_id))

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
    ) -> Path:
        downloader = self._pdf_downloader()
        pdf_url = candidate.pdf_url or candidate.url
        if not pdf_url:
            raise AcquisitionError("Resolved full text is missing a PDF URL")

        downloaded = downloader.download(pdf_url)
        path = pdf_path(self.config.data_dir, str(paper_id))
        atomic_write_bytes(path, downloaded.content)
        return path

    def _store_local_pdf(self, conn, *, paper_id: int, source_path: Path) -> Path:
        """Copy a local PDF to the data directory and record it."""
        pdf_content = source_path.read_bytes()
        path = pdf_path(self.config.data_dir, str(paper_id))
        atomic_write_bytes(path, pdf_content)
        return path

    def _chunk_and_store(self, conn, *, paper_id: int, paper_uuid: str, tei_xml: str) -> list[Chunk]:
        from retrieval.storage.models import generate_chunk_id
        
        chunker = self._tei_chunker()
        tei_chunks: list[TEIChunk] = chunker.chunk(tei_xml)
        chunk_models = [
            Chunk(
                chunk_id=generate_chunk_id(paper_uuid, chunk.position),
                paper_id=paper_id,
                paper_uuid=paper_uuid,
                kind=chunk.kind,
                position=chunk.position,
                section_title=chunk.section_title,
                order_in_section=chunk.order_in_section,
                content=chunk.text,
                citations=chunk.citations,
                tei_id=chunk.tei_id,
                tei_xpath=chunk.tei_xpath,
            )
            for chunk in tei_chunks
        ]
        return insert_chunks(conn, chunk_models)

    def _cleanup_downloaded_pdf(
        self, conn, *, paper_id: int, pdf_path_on_disk: Path | None
    ) -> None:
        """Remove downloaded PDF assets once processing has completed."""

        if pdf_path_on_disk and pdf_path_on_disk.exists():
            try:
                pdf_path_on_disk.unlink()
            except OSError:
                pass

    def _extract_citations(self, text: str) -> list[str]:
        return extract_citations(text)

    def _index_chunks(self, chunks: list[Chunk]) -> None:
        """Index chunks in ChromaDB."""
        rows = [
            (str(chunk.id), chunk.content) for chunk in chunks if chunk.id is not None
        ]
        if rows:
            self._chroma_index().add_documents(rows)

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
        return GrobidClient(str(self.config.grobid_url), timeout=self.config.request_timeout_s)

    def _tei_chunker(self) -> TEIChunker:
        return TEIChunker()

    def _chroma_index(self) -> ChromaIndex:
        return ChromaIndex(
            index_dir=self.config.index_dir,
            collection_name=self.index_name,
            chroma_url=self.config.chroma_url,
        )
