from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from psycopg import Connection

from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine
from retrieval.retrieval.types import ChunkSearchResult
from retrieval.storage.dao import (
    get_all_chunks,
    get_all_papers,
    get_chunks_for_paper,
    get_paper_authors,
    get_paper_files,
    get_paper_sources,
    get_papers_by_ids,
)
from retrieval.storage.db import get_connection
from retrieval.storage.models import (
    Chunk,
    ChunkKind,
    Paper,
    PaperAuthor,
    PaperFile,
    PaperChunkOutput,
    PaperRecordOutput,
    AuthorOutput,
    VenueOutput,
    FingerprintsOutput,
    ProvenanceOutput,
    ParserOutput,
    PdfAnchorOutput,
    TeiAnchorOutput,
    CharRangeOutput,
    ExternalSource,
    VenueType,
)


def _read_tei_xml(files: Sequence[PaperFile]) -> str | None:
    for file in files:
        if file.file_type != "tei" or not file.location:
            continue
        tei_path = Path(file.location)
        if not tei_path.is_file():
            continue
        try:
            return tei_path.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _serialize_chunk_output(chunk: Chunk) -> dict[str, Any]:
    """Serialize a Chunk to the PaperChunk JSON schema format."""
    output = PaperChunkOutput(
        chunk_id=chunk.chunk_id,
        paper_id=chunk.paper_uuid,
        kind=ChunkKind(chunk.kind),
        position=chunk.position,
        title=chunk.section_title,
        order_in_section=chunk.order_in_section,
        pdf=PdfAnchorOutput(
            page_start=chunk.pdf_page_start,
            page_end=chunk.pdf_page_end,
            bbox=chunk.pdf_bbox,
        ) if chunk.pdf_page_start or chunk.pdf_page_end or chunk.pdf_bbox else None,
        tei=TeiAnchorOutput(
            tei_id=chunk.tei_id,
            xpath=chunk.tei_xpath,
        ) if chunk.tei_id or chunk.tei_xpath else None,
        char_range=CharRangeOutput(
            start=chunk.char_start,
            end=chunk.char_end,
        ) if chunk.char_start is not None or chunk.char_end is not None else None,
        text=chunk.content,
        citations=chunk.citations or [],
    )
    return output.model_dump(mode="json", exclude_none=True)


def _serialize_paper_record_output(
    paper: Paper,
    authors: Sequence[PaperAuthor],
) -> dict[str, Any]:
    """Serialize a Paper to the PaperRecord JSON schema format."""
    # Determine external source - use the paper's stored value if available
    if paper.external_source:
        external_source = ExternalSource(paper.external_source)
    elif paper.doi:
        external_source = ExternalSource.DOI
    else:
        # Default to None if no clear external source is known
        external_source = None
    
    # Use the paper's stored external_id, falling back to DOI if external_source is DOI
    if paper.external_id:
        external_id = paper.external_id
    elif external_source == ExternalSource.DOI and paper.doi:
        external_id = paper.doi
    else:
        external_id = None
    
    # Convert authors
    author_outputs = [
        AuthorOutput(
            name=author.author_name,
            orcid=author.orcid,
            affiliations=author.affiliations or [],
        )
        for author in authors
    ]
    
    # Build venue if available
    venue = None
    if paper.venue_name or paper.venue_type or paper.venue_publisher:
        venue = VenueOutput(
            name=paper.venue_name,
            type=VenueType(paper.venue_type) if paper.venue_type else None,
            publisher=paper.venue_publisher,
        )
    
    # Format publication date
    publication_date = None
    if paper.published_at:
        publication_date = paper.published_at.isoformat()
    
    # Build fingerprints
    content_hash = paper.content_hash or "sha256:unknown"
    fingerprints = FingerprintsOutput(
        content_hash=content_hash,
        pdf_sha256=paper.pdf_sha256,
    )
    
    # Build provenance
    provenance = ProvenanceOutput(
        source=paper.provenance_source or "unknown",
        parser=ParserOutput(
            name="grobid" if paper.parser_name == "grobid" else "other",
            version=paper.parser_version or "unknown",
        ),
        ingested_at=paper.ingested_at or paper.created_at or datetime.now(),
        parser_warnings=paper.parser_warnings or [],
    )
    
    output = PaperRecordOutput(
        paper_id=paper.paper_id,
        external_source=external_source,
        external_id=external_id,
        title=paper.title,
        authors=author_outputs,
        venue=venue,
        publication_date=publication_date,
        abstract=paper.abstract,
        keywords=paper.keywords or [],
        fingerprints=fingerprints,
        provenance=provenance,
    )
    return output.model_dump(mode="json", exclude_none=True)


def _serialize_chunk(chunk: Chunk) -> dict[str, Any]:
    """Legacy serialization - now delegates to output format."""
    return _serialize_chunk_output(chunk)


def _serialize_paper(
    conn: Connection, paper: Paper, *, include_chunks: bool = False
) -> dict[str, Any]:
    """Serialize paper and related data to the new JSON schema format."""
    if paper.id is None:
        raise ValueError("Paper must have an id to serialize")

    authors = get_paper_authors(conn, paper.id)
    
    # Build the paper record output
    paper_record = _serialize_paper_record_output(paper, authors)
    
    payload: dict[str, Any] = paper_record

    if include_chunks:
        chunks = get_chunks_for_paper(conn, paper.id)
        payload["chunks"] = [_serialize_chunk_output(chunk) for chunk in chunks]

    return payload


def _serialize_search_result(
    result: ChunkSearchResult, paper: dict[str, Any] | None
) -> dict[str, Any]:
    """Serialize a search result to the PaperChunk JSON schema format."""
    section_path = list(result.section_path) if result.section_path else ["body"]
    
    chunk_output = PaperChunkOutput(
        chunk_id=result.chunk_id,
        paper_id=result.paper_uuid,
        kind=ChunkKind(result.kind),
        position=result.position,
        section_path=section_path,
        section_title=result.section_title,
        order_in_section=result.order_in_section,
        text=TextOutput(
            content=result.content,
            language=result.language,
        ),
        citations=list(result.citations),
    )
    
    chunk_dict = chunk_output.model_dump(mode="json", exclude_none=True)
    chunk_dict["score"] = result.score  # Add score for search results
    
    return {
        "chunk": chunk_dict,
        "paper": paper,
    }


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def handle_index(args: argparse.Namespace) -> None:
    config = RetrievalConfig()
    engine = RetrievalEngine(config)
    paper = engine.ingest_from_url(args.url)

    conn = get_connection(config.db_dsn)
    try:
        payload = _serialize_paper(conn, paper, include_chunks=True)
    finally:
        conn.close()

    _print_json(payload)


def handle_papers(args: argparse.Namespace) -> None:
    config = RetrievalConfig()
    conn = get_connection(config.db_dsn)
    try:
        papers = get_all_papers(conn)
        payload = [_serialize_paper(conn, paper) for paper in papers if paper.id is not None]
    finally:
        conn.close()

    _print_json(payload)


def handle_chunks(args: argparse.Namespace) -> None:
    config = RetrievalConfig()
    conn = get_connection(config.db_dsn)
    try:
        chunks = get_all_chunks(conn)
        paper_ids = {chunk.paper_id for chunk in chunks}
        paper_lookup = {
            paper.id: paper
            for paper in get_papers_by_ids(conn, list(paper_ids))
            if paper.id is not None
        }

        paper_cache: dict[int, dict[str, Any]] = {}
        payload = []
        for chunk in chunks:
            paper_id = chunk.paper_id
            if paper_id not in paper_cache:
                paper = paper_lookup.get(paper_id)
                paper_cache[paper_id] = (
                    _serialize_paper(conn, paper) if paper is not None else None
                )
            payload.append(
                {
                    "chunk": _serialize_chunk(chunk),
                    "paper": paper_cache.get(paper_id),
                }
            )
    finally:
        conn.close()

    _print_json(payload)


def handle_query(args: argparse.Namespace) -> None:
    config = RetrievalConfig()
    engine = RetrievalEngine(config)
    results = engine.search(args.query, top_k=5)

    conn = get_connection(config.db_dsn)
    try:
        paper_ids = {result.paper_id for result in results}
        paper_lookup = {
            paper.id: paper
            for paper in get_papers_by_ids(conn, list(paper_ids))
            if paper.id is not None
        }

        paper_cache: dict[int, dict[str, Any]] = {}
        payload = []
        for result in results:
            paper = paper_lookup.get(result.paper_id)
            if paper and result.paper_id not in paper_cache:
                paper_cache[result.paper_id] = _serialize_paper(conn, paper)
            payload.append(
                _serialize_search_result(result, paper_cache.get(result.paper_id))
            )
    finally:
        conn.close()

    _print_json(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scientific retrieval CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Ingest a PDF from a URL")
    index_parser.add_argument("url", help="URL pointing to a PDF to ingest")
    index_parser.set_defaults(func=handle_index)

    query_parser = subparsers.add_parser("query", help="Search indexed chunks")
    query_parser.add_argument("query", help="Query string to search for")
    query_parser.set_defaults(func=handle_query)

    papers_parser = subparsers.add_parser(
        "papers", help="List all indexed papers with metadata"
    )
    papers_parser.set_defaults(func=handle_papers)

    chunks_parser = subparsers.add_parser(
        "chunks", help="List all indexed chunks with metadata"
    )
    chunks_parser.set_defaults(func=handle_chunks)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
