"""Database utilities for PostgreSQL interactions."""

from __future__ import annotations

import os
from typing import Iterable, Set

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from retrieval.exceptions import ConfigError, DatabaseError


def get_connection(dsn: str | None = None) -> Connection:
    """Create a PostgreSQL connection using the provided or environment DSN."""

    resolved_dsn = dsn or os.getenv("RETRIEVAL_DB_DSN")
    if not resolved_dsn:
        raise ConfigError(
            "Database DSN is not configured. Set RETRIEVAL_DB_DSN or pass dsn explicitly."
        )

    try:
        return psycopg.connect(resolved_dsn)
    except Exception as exc:  # pragma: no cover - passthrough for better context
        raise DatabaseError(f"Failed to connect to database: {exc}") from exc


def fetch_existing_tables(conn: Connection, table_names: Iterable[str]) -> Set[str]:
    """Return the subset of ``table_names`` that exist in the current database."""

    names = tuple(table_names)
    if not names:
        return set()

    query = """
        SELECT tablename
        FROM pg_catalog.pg_tables
        WHERE schemaname = current_schema()
          AND tablename = ANY(%s)
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (list(names),))
        return {row["tablename"] for row in cur.fetchall()}
