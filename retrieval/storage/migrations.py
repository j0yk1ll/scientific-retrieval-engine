"""Migration utilities for running Alembic migrations programmatically."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def get_alembic_config(dsn: str | None = None) -> Config:
    """Create Alembic configuration object."""
    # Find alembic.ini relative to this file
    project_root = Path(__file__).resolve().parent.parent.parent
    alembic_ini = project_root / "alembic.ini"
    
    config = Config(str(alembic_ini))
    
    # Override with DSN if provided
    resolved_dsn = dsn or os.getenv("RETRIEVAL_DB_DSN")
    if resolved_dsn:
        # Convert postgresql:// to postgresql+psycopg:// for SQLAlchemy compatibility
        if resolved_dsn.startswith("postgresql://"):
            resolved_dsn = resolved_dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        config.set_main_option("sqlalchemy.url", resolved_dsn)
    
    return config


def run_migrations(dsn: str | None = None) -> None:
    """Run all pending migrations to head."""
    config = get_alembic_config(dsn)
    command.upgrade(config, "head")


def downgrade_migrations(dsn: str | None = None, revision: str = "-1") -> None:
    """Downgrade migrations."""
    config = get_alembic_config(dsn)
    command.downgrade(config, revision)
