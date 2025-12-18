"""Schema v2: Add paper and chunk fields for new JSON schemas

Revision ID: 20251217_schema_v2
Revises: 202502260001
Create Date: 2025-12-17 00:00:00.000000
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251217_schema_v2"
down_revision: Union[str, None] = "202502260001"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────────────────
    # Papers table additions
    # ─────────────────────────────────────────────────────────────────────────
    
    # Add paper_id (UUID) column
    op.add_column(
        "papers",
        sa.Column("paper_id", sa.Text(), nullable=True),
    )
    # Backfill existing rows with generated UUIDs
    op.execute("UPDATE papers SET paper_id = gen_random_uuid()::text WHERE paper_id IS NULL")
    op.alter_column("papers", "paper_id", nullable=False)
    op.create_unique_constraint("uq_papers_paper_id", "papers", ["paper_id"])
    
    # External source fields
    op.add_column(
        "papers",
        sa.Column("external_source", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("external_id", sa.Text(), nullable=True),
    )
    
    # Venue fields
    op.add_column(
        "papers",
        sa.Column("venue_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("venue_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("venue_publisher", sa.Text(), nullable=True),
    )
    
    # Keywords
    op.add_column(
        "papers",
        sa.Column(
            "keywords",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    
    # Fingerprints
    op.add_column(
        "papers",
        sa.Column("content_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("pdf_sha256", sa.Text(), nullable=True),
    )
    
    # Provenance
    op.add_column(
        "papers",
        sa.Column("provenance_source", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("parser_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("parser_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column(
            "parser_warnings",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "papers",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Paper authors table additions
    # ─────────────────────────────────────────────────────────────────────────
    
    # Rename affiliation to affiliations (JSONB array)
    op.add_column(
        "paper_authors",
        sa.Column(
            "affiliations",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Migrate existing affiliation data
    op.execute("""
        UPDATE paper_authors 
        SET affiliations = CASE 
            WHEN affiliation IS NOT NULL THEN jsonb_build_array(affiliation) 
            ELSE '[]'::jsonb 
        END
    """)
    op.drop_column("paper_authors", "affiliation")
    
    # Add ORCID
    op.add_column(
        "paper_authors",
        sa.Column("orcid", sa.Text(), nullable=True),
    )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Chunks table additions
    # ─────────────────────────────────────────────────────────────────────────
    
    # Add chunk_id (stable identifier)
    op.add_column(
        "chunks",
        sa.Column("chunk_id", sa.Text(), nullable=True),
    )
    # Backfill existing rows
    op.execute("""
        UPDATE chunks c 
        SET chunk_id = (
            SELECT p.paper_id || ':chunk:' || c.chunk_order 
            FROM papers p 
            WHERE p.id = c.paper_id
        )
        WHERE chunk_id IS NULL
    """)
    op.alter_column("chunks", "chunk_id", nullable=False)
    op.create_unique_constraint("uq_chunks_chunk_id", "chunks", ["chunk_id"])
    
    # Add paper_uuid (reference to paper.paper_id)
    op.add_column(
        "chunks",
        sa.Column("paper_uuid", sa.Text(), nullable=True),
    )
    op.execute("""
        UPDATE chunks c 
        SET paper_uuid = (SELECT p.paper_id FROM papers p WHERE p.id = c.paper_id)
        WHERE paper_uuid IS NULL
    """)
    op.alter_column("chunks", "paper_uuid", nullable=False)
    
    # Rename chunk_order to position
    op.alter_column("chunks", "chunk_order", new_column_name="position")
    
    # Add kind
    op.add_column(
        "chunks",
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            server_default="section_paragraph",
        ),
    )
    
    # Convert section to section_path (JSONB array)
    op.add_column(
        "chunks",
        sa.Column(
            "section_path",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Migrate existing section data (split by " > ")
    op.execute("""
        UPDATE chunks 
        SET section_path = CASE 
            WHEN section IS NOT NULL AND section != '' 
            THEN to_jsonb(string_to_array(section, ' > '))
            ELSE '[]'::jsonb 
        END
    """)
    
    # Add section_title
    op.add_column(
        "chunks",
        sa.Column("section_title", sa.Text(), nullable=True),
    )
    # Copy last element of section as section_title
    op.execute("""
        UPDATE chunks 
        SET section_title = CASE 
            WHEN section IS NOT NULL AND section != '' 
            THEN split_part(section, ' > ', array_length(string_to_array(section, ' > '), 1))
            ELSE NULL 
        END
    """)
    
    # Drop old section column
    op.drop_column("chunks", "section")
    
    # Add order_in_section
    op.add_column(
        "chunks",
        sa.Column("order_in_section", sa.Integer(), nullable=True),
    )
    
    # Add language
    op.add_column(
        "chunks",
        sa.Column("language", sa.Text(), nullable=True),
    )
    
    # PDF anchoring
    op.add_column(
        "chunks",
        sa.Column("pdf_page_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("pdf_page_end", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "pdf_bbox",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    
    # TEI anchoring
    op.add_column(
        "chunks",
        sa.Column("tei_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("tei_xpath", sa.Text(), nullable=True),
    )
    
    # Character range
    op.add_column(
        "chunks",
        sa.Column("char_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("char_end", sa.Integer(), nullable=True),
    )
    
    # Create indexes
    op.create_index("idx_papers_paper_id", "papers", ["paper_id"])
    op.create_index("idx_papers_external_source_id", "papers", ["external_source", "external_id"])
    op.create_index("idx_chunks_chunk_id", "chunks", ["chunk_id"])
    op.create_index("idx_chunks_paper_uuid", "chunks", ["paper_uuid"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_chunks_paper_uuid")
    op.drop_index("idx_chunks_chunk_id")
    op.drop_index("idx_papers_external_source_id")
    op.drop_index("idx_papers_paper_id")
    
    # Chunks: restore section from section_path
    op.add_column(
        "chunks",
        sa.Column("section", sa.Text(), nullable=True),
    )
    op.execute("""
        UPDATE chunks 
        SET section = CASE 
            WHEN jsonb_array_length(section_path) > 0 
            THEN array_to_string(ARRAY(SELECT jsonb_array_elements_text(section_path)), ' > ')
            ELSE NULL 
        END
    """)
    
    # Drop new chunk columns
    op.drop_column("chunks", "char_end")
    op.drop_column("chunks", "char_start")
    op.drop_column("chunks", "tei_xpath")
    op.drop_column("chunks", "tei_id")
    op.drop_column("chunks", "pdf_bbox")
    op.drop_column("chunks", "pdf_page_end")
    op.drop_column("chunks", "pdf_page_start")
    op.drop_column("chunks", "language")
    op.drop_column("chunks", "order_in_section")
    op.drop_column("chunks", "section_title")
    op.drop_column("chunks", "section_path")
    op.drop_column("chunks", "kind")
    op.alter_column("chunks", "position", new_column_name="chunk_order")
    op.drop_constraint("uq_chunks_chunk_id", "chunks")
    op.drop_column("chunks", "paper_uuid")
    op.drop_column("chunks", "chunk_id")
    
    # Paper authors: restore affiliation
    op.add_column(
        "paper_authors",
        sa.Column("affiliation", sa.Text(), nullable=True),
    )
    op.execute("""
        UPDATE paper_authors 
        SET affiliation = CASE 
            WHEN jsonb_array_length(affiliations) > 0 
            THEN affiliations->>0 
            ELSE NULL 
        END
    """)
    op.drop_column("paper_authors", "orcid")
    op.drop_column("paper_authors", "affiliations")
    
    # Drop new paper columns
    op.drop_column("papers", "ingested_at")
    op.drop_column("papers", "parser_warnings")
    op.drop_column("papers", "parser_version")
    op.drop_column("papers", "parser_name")
    op.drop_column("papers", "provenance_source")
    op.drop_column("papers", "pdf_sha256")
    op.drop_column("papers", "content_hash")
    op.drop_column("papers", "keywords")
    op.drop_column("papers", "venue_publisher")
    op.drop_column("papers", "venue_type")
    op.drop_column("papers", "venue_name")
    op.drop_column("papers", "external_id")
    op.drop_column("papers", "external_source")
    op.drop_constraint("uq_papers_paper_id", "papers")
    op.drop_column("papers", "paper_id")
