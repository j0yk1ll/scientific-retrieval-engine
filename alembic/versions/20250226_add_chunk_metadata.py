"""add chunk metadata columns

Revision ID: 202502260001
Revises: 2a65b2e7cc1f
Create Date: 2025-02-26 00:01:00.000000
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "202502260001"
down_revision: Union[str, None] = "2a65b2e7cc1f"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("section", sa.Text(), nullable=True))
    op.add_column(
        "chunks",
        sa.Column(
            "citations",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "citations")
    op.drop_column("chunks", "section")
