"""add published_post_backups table

Stores a byte-for-byte snapshot of each main-channel post (caption HTML,
mirrored image URLs, button layout, divider sticker) so the whole channel can
be rebuilt on a fresh channel after a ban — no re-rendering or re-fetching.

Revision ID: 0012_add_published_post_backups
Revises: 0011_admin_pool_weight_hours
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_add_published_post_backups"
down_revision: str | None = "0011_admin_pool_weight_hours"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "published_post_backups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("anime_doc_id", sa.String(48), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), server_default="", nullable=False),
        sa.Column("image_source_url", sa.Text(), nullable=True),
        sa.Column("image_catbox_url", sa.Text(), nullable=True),
        sa.Column("image_telegraph_url", sa.Text(), nullable=True),
        sa.Column("button_data", postgresql.JSONB(), nullable=True),
        sa.Column("divider_sticker_id", sa.Text(), nullable=True),
        sa.Column("source_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_published_post_backups")),
    )
    op.create_index(
        op.f("ix_published_post_backups_anime_doc_id"),
        "published_post_backups", ["anime_doc_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_published_post_backups_anime_doc_id"),
        table_name="published_post_backups",
    )
    op.drop_table("published_post_backups")
