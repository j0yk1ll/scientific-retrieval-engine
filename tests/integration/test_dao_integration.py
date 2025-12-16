import os
from datetime import date
from typing import List

import pytest

from retrieval.storage.dao import (
    get_chunks_by_ids,
    insert_chunks,
    insert_paper_source,
    replace_authors,
    upsert_paper,
    upsert_paper_files,
)
from retrieval.storage.db import get_connection
from retrieval.storage.models import Chunk, Paper, PaperAuthor, PaperFile, PaperSource
from retrieval.storage.migrations import run_migrations


@pytest.mark.skipif(
    os.getenv("RETRIEVAL_DB_DSN") is None,
    reason="RETRIEVAL_DB_DSN not set",
)
def test_dao_crud_round_trip() -> None:
    dsn = os.getenv("RETRIEVAL_DB_DSN")
    run_migrations(dsn=dsn)

    with get_connection(dsn) as conn:
        new_paper = Paper(
            title="Integration Testing in Retrieval Engines",
            abstract="Testing CRUD operations against Postgres",
            doi="10.1234/example",
            published_at=date(2024, 12, 31),
        )
        persisted_paper = upsert_paper(conn, new_paper)
        assert persisted_paper.id is not None
        assert persisted_paper.created_at is not None

        updated_paper = upsert_paper(
            conn,
            persisted_paper.model_copy(update={"title": "Updated Title for Integration"}),
        )
        assert updated_paper.id == persisted_paper.id
        assert updated_paper.title == "Updated Title for Integration"
        assert updated_paper.updated_at is not None
        assert updated_paper.updated_at >= persisted_paper.updated_at

        authors: List[PaperAuthor] = [
            PaperAuthor(paper_id=updated_paper.id, author_name="Alice", author_order=1),
            PaperAuthor(paper_id=updated_paper.id, author_name="Bob", author_order=2),
        ]
        inserted_authors = replace_authors(conn, updated_paper.id, authors)
        assert [a.author_name for a in inserted_authors] == ["Alice", "Bob"]

        replacement_authors = [
            PaperAuthor(paper_id=updated_paper.id, author_name="Carol", author_order=1),
        ]
        replaced = replace_authors(conn, updated_paper.id, replacement_authors)
        assert len(replaced) == 1
        assert replaced[0].author_name == "Carol"

        first_files = [
            PaperFile(
                paper_id=updated_paper.id,
                file_type="pdf",
                location="s3://bucket/paper.pdf",
                checksum="abc123",
            )
        ]
        inserted_files = upsert_paper_files(conn, updated_paper.id, first_files)
        assert len(inserted_files) == 1
        assert inserted_files[0].location.endswith("paper.pdf")

        latest_files = [
            PaperFile(
                paper_id=updated_paper.id,
                file_type="pdf",
                location="s3://bucket/paper-v2.pdf",
                checksum="def456",
            ),
            PaperFile(
                paper_id=updated_paper.id,
                file_type="tei",
                location="s3://bucket/paper.tei.xml",
                checksum=None,
            ),
        ]
        refreshed_files = upsert_paper_files(conn, updated_paper.id, latest_files)
        assert {f.file_type for f in refreshed_files} == {"pdf", "tei"}
        pdf_record = next(f for f in refreshed_files if f.file_type == "pdf")
        assert pdf_record.location.endswith("paper-v2.pdf")

        source = PaperSource(
            paper_id=updated_paper.id,
            source_name="OpenAlex",
            source_identifier="A-123",
            metadata={"ingested_by": "integration-test"},
        )
        persisted_source = insert_paper_source(conn, source)
        assert persisted_source.id is not None
        assert persisted_source.metadata == {"ingested_by": "integration-test"}

        to_insert = [
            Chunk(paper_id=updated_paper.id, chunk_order=0, content="chunk 0"),
            Chunk(paper_id=updated_paper.id, chunk_order=1, content="chunk 1"),
        ]
        inserted_chunks = insert_chunks(conn, to_insert)
        chunk_ids = [chunk.id for chunk in inserted_chunks]
        assert chunk_ids[0] is not None

        fetched_chunks = get_chunks_by_ids(conn, list(reversed(chunk_ids)))
        assert [chunk.content for chunk in fetched_chunks] == ["chunk 0", "chunk 1"]
        assert fetched_chunks[0].chunk_order == 0
