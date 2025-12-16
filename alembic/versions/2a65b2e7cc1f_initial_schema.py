"""initial_schema

Revision ID: 2a65b2e7cc1f
Revises: 
Create Date: 2025-12-16 08:37:06.965863

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a65b2e7cc1f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable pg_trgm extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    
    # Create papers table
    op.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            abstract TEXT,
            doi TEXT,
            published_at DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    
    # Create paper_authors table
    op.execute("""
        CREATE TABLE IF NOT EXISTS paper_authors (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            author_name TEXT NOT NULL,
            author_order INT NOT NULL,
            affiliation TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    
    # Create paper_sources table
    op.execute("""
        CREATE TABLE IF NOT EXISTS paper_sources (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            source_name TEXT NOT NULL,
            source_identifier TEXT,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    
    # Create paper_files table
    op.execute("""
        CREATE TABLE IF NOT EXISTS paper_files (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            location TEXT NOT NULL,
            checksum TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    
    # Create chunks table
    op.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            chunk_order INT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    
    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_papers_title_trgm ON papers USING gin (title gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_paper_id ON chunks (paper_id)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_chunks_paper_id")
    op.execute("DROP INDEX IF EXISTS idx_papers_title_trgm")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS paper_files")
    op.execute("DROP TABLE IF EXISTS paper_sources")
    op.execute("DROP TABLE IF EXISTS paper_authors")
    op.execute("DROP TABLE IF EXISTS papers")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
