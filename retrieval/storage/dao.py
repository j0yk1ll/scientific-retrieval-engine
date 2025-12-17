"""Data-access layer for CRUD operations on storage entities."""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Sequence

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from retrieval.storage.models import Chunk, Paper, PaperAuthor, PaperFile, PaperSource


def _serialize_metadata(metadata: dict | None) -> dict | None:
    """Convert non-JSON-serializable types (like datetime.date) to JSON-compatible formats."""
    if metadata is None:
        return None
    
    def _convert_value(value: Any) -> Any:
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: _convert_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [_convert_value(item) for item in value]
        return value
    
    return {k: _convert_value(v) for k, v in metadata.items()}


def upsert_paper(conn: Connection, paper: Paper) -> Paper:
    """Insert or update a paper record and return the persisted model."""

    insert_sql = (
        """
        INSERT INTO papers (title, abstract, doi, published_at)
        VALUES (%s, %s, %s, %s)
        RETURNING id, title, abstract, doi, published_at, created_at, updated_at
        """
    )
    upsert_sql = (
        """
        INSERT INTO papers (id, title, abstract, doi, published_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
            SET title = EXCLUDED.title,
                abstract = EXCLUDED.abstract,
                doi = EXCLUDED.doi,
                published_at = EXCLUDED.published_at,
                updated_at = now()
        RETURNING id, title, abstract, doi, published_at, created_at, updated_at
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        if paper.id is None:
            cur.execute(
                insert_sql,
                (paper.title, paper.abstract, paper.doi, paper.published_at),
            )
        else:
            cur.execute(
                upsert_sql,
                (
                    paper.id,
                    paper.title,
                    paper.abstract,
                    paper.doi,
                    paper.published_at,
                ),
            )
        row = cur.fetchone()
    return Paper.model_validate(row)


def replace_authors(conn: Connection, paper_id: int, authors: Sequence[PaperAuthor]) -> list[PaperAuthor]:
    """Replace all authors for ``paper_id`` with the provided sequence."""

    inserted: list[PaperAuthor] = []
    delete_sql = "DELETE FROM paper_authors WHERE paper_id = %s"
    insert_sql = (
        """
        INSERT INTO paper_authors (paper_id, author_name, author_order, affiliation)
        VALUES (%s, %s, %s, %s)
        RETURNING id, paper_id, author_name, author_order, affiliation, created_at
        """
    )

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(delete_sql, (paper_id,))
            for author in authors:
                cur.execute(
                    insert_sql,
                    (
                        paper_id,
                        author.author_name,
                        author.author_order,
                        author.affiliation,
                    ),
                )
                inserted.append(PaperAuthor.model_validate(cur.fetchone()))
    return inserted


def get_paper_authors(conn: Connection, paper_id: int) -> list[PaperAuthor]:
    """Fetch authors for a paper ordered by author list position."""

    sql = (
        """
        SELECT id, paper_id, author_name, author_order, affiliation, created_at
        FROM paper_authors
        WHERE paper_id = %s
        ORDER BY author_order, id
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (paper_id,))
        rows = cur.fetchall()
    return [PaperAuthor.model_validate(row) for row in rows]


def upsert_paper_files(conn: Connection, paper_id: int, files: Sequence[PaperFile]) -> list[PaperFile]:
    """Upsert paper files by deleting existing matches and inserting the new rows."""

    if not files:
        return []

    file_types = [file.file_type for file in files]
    inserted: list[PaperFile] = []
    delete_sql = "DELETE FROM paper_files WHERE paper_id = %s AND file_type = ANY(%s)"
    insert_sql = (
        """
        INSERT INTO paper_files (paper_id, file_type, location, checksum)
        VALUES (%s, %s, %s, %s)
        RETURNING id, paper_id, file_type, location, checksum, created_at
        """
    )

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(delete_sql, (paper_id, file_types))
            for file in files:
                cur.execute(
                    insert_sql,
                    (paper_id, file.file_type, file.location, file.checksum),
                )
                inserted.append(PaperFile.model_validate(cur.fetchone()))
    return inserted


def delete_paper_files(conn: Connection, paper_id: int, file_types: Sequence[str]) -> None:
    """Remove file records for ``paper_id`` that match ``file_types``."""

    if not file_types:
        return

    sql = "DELETE FROM paper_files WHERE paper_id = %s AND file_type = ANY(%s)"

    with conn.cursor() as cur:
        cur.execute(sql, (paper_id, list(file_types)))


def get_paper_files(conn: Connection, paper_id: int) -> list[PaperFile]:
    """Fetch file records for a paper ordered by creation time."""

    sql = (
        """
        SELECT id, paper_id, file_type, location, checksum, created_at
        FROM paper_files
        WHERE paper_id = %s
        ORDER BY created_at DESC, id DESC
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (paper_id,))
        rows = cur.fetchall()
    return [PaperFile.model_validate(row) for row in rows]


def insert_paper_source(conn: Connection, source: PaperSource) -> PaperSource:
    """Insert a paper source and return the persisted record."""

    sql = (
        """
        INSERT INTO paper_sources (paper_id, source_name, source_identifier, metadata)
        VALUES (%s, %s, %s, %s)
        RETURNING id, paper_id, source_name, source_identifier, metadata, created_at
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            sql,
            (
                source.paper_id,
                source.source_name,
                source.source_identifier,
                Json(_serialize_metadata(source.metadata)),
            ),
        )
        row = cur.fetchone()
    return PaperSource.model_validate(row)


def get_paper_sources(conn: Connection, paper_id: int) -> list[PaperSource]:
    """Fetch provenance entries for a paper ordered by creation time."""

    sql = (
        """
        SELECT id, paper_id, source_name, source_identifier, metadata, created_at
        FROM paper_sources
        WHERE paper_id = %s
        ORDER BY created_at DESC, id DESC
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (paper_id,))
        rows = cur.fetchall()
    return [PaperSource.model_validate(row) for row in rows]


def insert_chunks(conn: Connection, chunks: Iterable[Chunk]) -> list[Chunk]:
    """Insert a collection of chunks and return them with generated identifiers."""

    inserted: list[Chunk] = []
    sql = (
        """
        INSERT INTO chunks (paper_id, chunk_order, content)
        VALUES (%s, %s, %s)
        RETURNING id, paper_id, chunk_order, content, created_at
        """
    )

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            for chunk in chunks:
                cur.execute(sql, (chunk.paper_id, chunk.chunk_order, chunk.content))
                inserted.append(Chunk.model_validate(cur.fetchone()))
    return inserted


def get_chunks_by_ids(conn: Connection, chunk_ids: Sequence[int]) -> list[Chunk]:
    """Fetch chunks by their identifiers ordered deterministically by ``chunk_order``."""

    if not chunk_ids:
        return []

    sql = (
        """
        SELECT id, paper_id, chunk_order, content, created_at
        FROM chunks
        WHERE id = ANY(%s)
        ORDER BY chunk_order, id
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (list(chunk_ids),))
        rows = cur.fetchall()
    return [Chunk.model_validate(row) for row in rows]


def get_papers_by_ids(conn: Connection, paper_ids: Sequence[int]) -> list[Paper]:
    """Fetch paper metadata for a list of identifiers."""

    if not paper_ids:
        return []

    sql = (
        """
        SELECT id, title, abstract, doi, published_at, created_at, updated_at
        FROM papers
        WHERE id = ANY(%s)
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (list(paper_ids),))
        rows = cur.fetchall()
    return [Paper.model_validate(row) for row in rows]


def get_all_chunks(conn: Connection) -> list[Chunk]:
    """Fetch all chunks in the database ordered by ``id``."""

    sql = (
        """
        SELECT id, paper_id, chunk_order, content, created_at
        FROM chunks
        ORDER BY id
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [Chunk.model_validate(row) for row in rows]


def get_all_papers(conn: Connection) -> list[Paper]:
    """Fetch all papers ordered by creation time descending."""

    sql = (
        """
        SELECT id, title, abstract, doi, published_at, created_at, updated_at
        FROM papers
        ORDER BY created_at DESC, id DESC
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [Paper.model_validate(row) for row in rows]


def get_chunks_for_paper(conn: Connection, paper_id: int) -> list[Chunk]:
    """Fetch all chunks for a paper ordered by chunk sequence."""

    sql = (
        """
        SELECT id, paper_id, chunk_order, content, created_at
        FROM chunks
        WHERE paper_id = %s
        ORDER BY chunk_order, id
        """
    )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (paper_id,))
        rows = cur.fetchall()
    return [Chunk.model_validate(row) for row in rows]
