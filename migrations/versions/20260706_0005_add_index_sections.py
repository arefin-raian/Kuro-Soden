"""add index_sections table for dynamic index channel support

Creates the ``index_sections`` table that tracks the dynamic mapping
between displayed letter labels (e.g. "A", "A(2)", "B") and their
Telegram message IDs. Reserved (unused) slots have ``label = NULL``.

When a letter overflows Telegram's 1024-char caption limit, subsequent
sections shift down and reserved slots are consumed. The poster buttons
are rebuilt after every shift.

Revision ID: 0005_add_index_sections
Revises: 0004_add_storage_pack_entry_id
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_add_index_sections"
down_revision: str | None = "0004_add_storage_pack_entry_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: on the live DB this table was already auto-created by
    # ``Base.metadata.create_all`` (it's a brand-new table, so create_all picked
    # it up even though the alembic branch never ran). Skip if it already exists
    # so re-folding this migration into mainline history doesn't blow up.
    if sa.inspect(op.get_bind()).has_table("index_sections"):
        return
    op.create_table(
        "index_sections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            unique=True,
            index=True,
            nullable=False,
        ),
        sa.Column("label", sa.String(16), nullable=True),
        sa.Column("base_letter", sa.String(4), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("index_sections")
