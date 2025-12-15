import os
from pathlib import Path

import pytest

from retrieval.storage.db import fetch_existing_tables, get_connection
from scripts.migrate import run_migrations

REQUIRED_TABLES = {
    "schema_migrations",
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

    applied = run_migrations(dsn=dsn)
    # Ensure idempotency
    reapplied = run_migrations(dsn=dsn)
    assert reapplied == []

    with get_connection(dsn) as conn:
        existing_tables = fetch_existing_tables(conn, REQUIRED_TABLES)

    assert REQUIRED_TABLES.issubset(existing_tables)
    assert applied == [] or set(applied) == {"001_init.sql"}
