"""add channel_content_backups table

Wipe-proof snapshot of a distribution / index channel's content pack — the
sibling of ``published_post_backups`` (main channel) for the other two scopes.
A distribution channel's ordered card list (captions, mirrored images, buttons,
pins, footer message id) is stored here so a banned channel can be re-posted
verbatim on a fresh chat — no re-render, no re-fetch — even though
``recreate_bot`` deletes the live ``bot_content_posts`` rows first.

Revision ID: 0017_add_channel_content_backups
Revises: 0016_add_scheduled_posts
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017_add_channel_content_backups"
down_revision: str | None = "0016_add_scheduled_posts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_content_backups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("channel_key", sa.String(48), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("cards", postgresql.JSONB(), nullable=True),
        sa.Column("footer_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_content_backups")),
        sa.UniqueConstraint("scope", "channel_key", name="uq_channel_backup_scope_key"),
    )


def downgrade() -> None:
    op.drop_table("channel_content_backups")
