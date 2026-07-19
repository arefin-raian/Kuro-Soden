"""add channel_broadcasts table

Tracks each copy of an operator broadcast posted into a distribution channel so a
scheduled auto-deletion survives a restart. ``delete_at`` is when the message
should be removed (NULL = permanent); a scheduler sweep deletes past-due rows.
``batch_id`` groups every copy of one broadcast for reporting. The main channel
is never a target.

Revision ID: 0014_add_channel_broadcasts
Revises: 0013_add_channel_layout
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0014_add_channel_broadcasts"
down_revision: str | None = "0013_add_channel_layout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_broadcasts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("delete_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_broadcasts")),
    )
    op.create_index(
        op.f("ix_channel_broadcasts_batch_id"),
        "channel_broadcasts", ["batch_id"],
    )
    op.create_index(
        op.f("ix_channel_broadcasts_chat_id"),
        "channel_broadcasts", ["chat_id"],
    )
    op.create_index(
        op.f("ix_channel_broadcasts_delete_at"),
        "channel_broadcasts", ["delete_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_channel_broadcasts_delete_at"), table_name="channel_broadcasts")
    op.drop_index(op.f("ix_channel_broadcasts_chat_id"), table_name="channel_broadcasts")
    op.drop_index(op.f("ix_channel_broadcasts_batch_id"), table_name="channel_broadcasts")
    op.drop_table("channel_broadcasts")
