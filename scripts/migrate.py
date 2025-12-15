"""Migration runner for applying SQL migrations in order."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Set

from retrieval.storage.db import get_connection

MIGRATIONS_PATH = Path(__file__).resolve().parent.parent / "retrieval" / "storage" / "migrations"


def ensure_schema_migrations(conn) -> None:
    """Create the schema_migrations table if it does not yet exist."""

    with conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )


def fetch_applied(conn) -> Set[str]:
    """Return the set of already applied migration filenames."""

    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def discover_migrations(migrations_dir: Path) -> List[Path]:
    """List migration files in deterministic sorted order."""

    return sorted(migrations_dir.glob("*.sql"))


def apply_migration(conn, path: Path) -> None:
    """Execute a single migration file inside a transaction."""

    sql = path.read_text()
    with conn.transaction():
        conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s)",
            (path.name,),
        )


def run_migrations(dsn: str | None, migrations_dir: Path = MIGRATIONS_PATH) -> List[str]:
    """Apply all migrations in order, skipping those already recorded."""

    applied: List[str] = []
    with get_connection(dsn) as conn:
        ensure_schema_migrations(conn)
        already_applied = fetch_applied(conn)
        for migration in discover_migrations(migrations_dir):
            if migration.name in already_applied:
                continue
            apply_migration(conn, migration)
            applied.append(migration.name)
    return applied


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply SQL migrations to the database")
    parser.add_argument("--dsn", help="PostgreSQL DSN", required=False)
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=MIGRATIONS_PATH,
        help="Directory containing .sql migration files",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    applied = run_migrations(dsn=args.dsn, migrations_dir=args.migrations_dir)
    if applied:
        print("Applied migrations:", ", ".join(applied))
    else:
        print("No migrations to apply")


if __name__ == "__main__":
    main()
