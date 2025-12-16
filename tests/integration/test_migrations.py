import os
from pathlib import Path

import pytest

from retrieval.storage.db import fetch_existing_tables, get_connection
from retrieval.storage.migrations import run_migrations

REQUIRED_TABLES = {
    "alembic_version",
    "papers",
    "paper_authors",
    "paper_sources",
    "paper_files",
    "chunks",
}


@pytest.mark.skipif(
    os.getenv("RETRIEVAL_DB_DSN") is None,
    reason="RETRIEVAL_DB_DSN not set",
)
def test_migrations_apply_and_tables_exist(tmp_path: Path) -> None:
    dsn = os.getenv("RETRIEVAL_DB_DSN")

    # Run migrations (Alembic handles idempotency internally)
    run_migrations(dsn=dsn)
    # Running again should be safe
    run_migrations(dsn=dsn)

    with get_connection(dsn) as conn:
        existing_tables = fetch_existing_tables(conn, REQUIRED_TABLES)

    assert REQUIRED_TABLES.issubset(existing_tables)
