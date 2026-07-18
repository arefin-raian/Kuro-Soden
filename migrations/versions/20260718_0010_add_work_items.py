"""add work_items table

Admin-marshalled pipeline jobs, separate from user requests. Work items never
count against a user's request limit but flow into the same download queue.

Revision ID: 0010_add_work_items
Revises: 0009_add_request_code_sequence
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_add_work_items"
down_revision: str | None = "0009_add_request_code_sequence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("added_by_admin_id", sa.BigInteger(), nullable=False),
        sa.Column("anime_title", sa.String(length=256), nullable=False),
        sa.Column("anime_doc_id", sa.String(length=48), nullable=True),
        sa.Column("franchise_data", postgresql.JSONB(), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False,
                  server_default="download"),
        sa.Column("status", sa.String(length=16), nullable=False,
                  server_default="open"),
        sa.Column("assigned_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_work_items_code", "work_items", ["code"], unique=True)
    op.create_index("ix_work_items_added_by_admin_id", "work_items",
                    ["added_by_admin_id"])
    op.create_index("ix_work_items_anime_doc_id", "work_items", ["anime_doc_id"])
    op.create_index("ix_work_items_stage", "work_items", ["stage"])
    op.create_index("ix_work_items_status", "work_items", ["status"])
    op.create_index("ix_work_items_assigned_admin_id", "work_items",
                    ["assigned_admin_id"])


def downgrade() -> None:
    op.drop_index("ix_work_items_assigned_admin_id", table_name="work_items")
    op.drop_index("ix_work_items_status", table_name="work_items")
    op.drop_index("ix_work_items_stage", table_name="work_items")
    op.drop_index("ix_work_items_anime_doc_id", table_name="work_items")
    op.drop_index("ix_work_items_added_by_admin_id", table_name="work_items")
    op.drop_index("ix_work_items_code", table_name="work_items")
    op.drop_table("work_items")
