"""add distribution entity type columns (is_channel, chat_id)

Adds ``is_channel`` and ``chat_id`` to the ``bots`` table so distribution
entities can represent both bot accounts and public Telegram channels.
Channels don't run Pyrogram clients — they're posted to directly via the
userbot pool.

Revision ID: 0006_add_distribution_entity_type
Revises: 0005_rename_to_cached_url
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_add_distribution_entity_type"
down_revision: str | None = "0005_rename_to_cached_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
        return column in cols
    except Exception:
        return False


def upgrade() -> None:
    if not _column_exists("bots", "is_channel"):
        op.add_column(
            "bots",
            sa.Column(
                "is_channel",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )
    if not _column_exists("bots", "chat_id"):
        op.add_column(
            "bots",
            sa.Column(
                "chat_id",
                sa.BigInteger(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _column_exists("bots", "is_channel"):
        op.drop_column("bots", "is_channel")
    if _column_exists("bots", "chat_id"):
        op.drop_column("bots", "chat_id")
