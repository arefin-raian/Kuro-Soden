"""add channel_layout table

Stores the ordered message layout (info/season/extra cards, dividers, watch
guide, footer) of each distribution channel's content pack, with the Telegram
message id of every message. Lets an incremental update (new franchise entry)
delete just the footer + trailing divider, append the new card(s), and re-post
a fresh divider + footer — no full re-render, main channel untouched.

Revision ID: 0013_add_channel_layout
Revises: 0012_add_published_post_backups
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0013_add_channel_layout"
down_revision: str | None = "0012_add_published_post_backups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_layout",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("channel_bot_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
        sa.Column("anilist_id", sa.BigInteger(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_bot_id"], ["bots.id"],
            name=op.f("fk_channel_layout_channel_bot_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_layout")),
    )
    op.create_index(
        op.f("ix_channel_layout_channel_bot_id"),
        "channel_layout", ["channel_bot_id"],
    )
    op.create_index(
        op.f("ix_channel_layout_anilist_id"),
        "channel_layout", ["anilist_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_channel_layout_anilist_id"), table_name="channel_layout")
    op.drop_index(op.f("ix_channel_layout_channel_bot_id"), table_name="channel_layout")
    op.drop_table("channel_layout")
