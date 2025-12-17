from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from psycopg import Connection

from retrieval.config import RetrievalConfig
from retrieval.engine import RetrievalEngine
from retrieval.parsing.citations import extract_citations
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
from retrieval.storage.models import Chunk, Paper, PaperFile


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


def _serialize_chunk(chunk: Chunk) -> dict[str, Any]:
    data = chunk.model_dump(mode="json")
    data["citations"] = extract_citations(chunk.content)
    return data


def _serialize_paper(
    conn: Connection, paper: Paper, *, include_chunks: bool = False
) -> dict[str, Any]:
    if paper.id is None:
        raise ValueError("Paper must have an id to serialize")

    authors = get_paper_authors(conn, paper.id)
    sources = get_paper_sources(conn, paper.id)
    files = get_paper_files(conn, paper.id)
    tei_xml = _read_tei_xml(files)

    payload: dict[str, Any] = {
        "paper": paper.model_dump(mode="json"),
        "authors": [author.model_dump(mode="json") for author in authors],
        "sources": [source.model_dump(mode="json") for source in sources],
        "files": [file.model_dump(mode="json") for file in files],
        "tei_xml": tei_xml,
    }

    if include_chunks:
        chunks = get_chunks_for_paper(conn, paper.id)
        payload["chunks"] = [_serialize_chunk(chunk) for chunk in chunks]

    return payload


def _serialize_search_result(
    result: ChunkSearchResult, paper: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "chunk": {
            "id": result.chunk_id,
            "paper_id": result.paper_id,
            "chunk_order": result.chunk_order,
            "content": result.content,
            "score": result.score,
            "citations": list(result.citations),
        },
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
