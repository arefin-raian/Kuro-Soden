"""distribution-bot pre-rendering + revision-driven redelivery

Three small additive changes that flush the change of generation target from
\"live-render on every /start\" to \"generate once on publish, deliver from storage\":

  * ``bot_content_posts.image_cached_url`` — the catbox.moe HTTPS URL written
    at ``generate_posts`` time by ``providers/catbox.upload_from_url``. The
    distribution bot serves this URL directly on ``/start`` so Telegram
    doesn't refetch from TMDB/AniList CDNs on every user /start. The column
    was added to the model with this name; migration ``0005`` handles the
    rename from an earlier round that reserved the slot as ``image_local_path``
    before the switch from the local-disk cache to catbox.moe.
  * ``bots.content_revision`` — monotonic counter, bumped by ``generate_posts``.
    Lets the distribution bot compare a returning user's last delivered
    revision against the current one and decide whether to delete-then-resend.
  * ``bot_deliveries`` — per ``(bot_id, user_id)`` row tracking the message IDs
    of what the bot last sent to that user, so the redelivery dance can find
    and clean them up across bot restarts (the scheduler-based cleanup alone
    would lose them on restart).

Idempotent: every ``add_column`` / ``op.create_table`` is preceded by an
\"already there? skip\" probe so this migration can run on a fresh DB (where
``auto_create_schema=True`` already materialised the model) or a production DB
that ran exactly the original migration 0003.

Revision ID: 0004_distribution_rev_delivery
Revises: 0003_add_bot_content_posts
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_distribution_rev_delivery"
down_revision: str | None = "0003_add_bot_content_posts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    """Best-effort introspection — if the inspector can't be reached we assume
    the column is missing so the migration proceeds (worst case: it errors
    cleanly with a duplicate-column, which Alembic will surface)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        cols = {c["name"] for c in insp.get_columns(table)}
        return column in cols
    except Exception:
        return False


def _table_exists(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return insp.has_table(table)
    except Exception:
        return False


def upgrade() -> None:
    # 1. bot_content_posts.image_local_path (model declares it; 0003 didn't add it).
    if not _column_exists("bot_content_posts", "image_local_path"):
        op.add_column(
            "bot_content_posts",
            sa.Column("image_local_path", sa.Text(), nullable=True),
        )

    # 2. bots.content_revision — bumped on every generate_posts run.
    if not _column_exists("bots", "content_revision"):
        op.add_column(
            "bots",
            sa.Column(
                "content_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    # 3. bot_deliveries — per (bot_id, user_id) delivery-tracking table.
    if not _table_exists("bot_deliveries"):
        op.create_table(
            "bot_deliveries",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("bot_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("chat_id", sa.BigInteger(), nullable=False),
            sa.Column(
                "message_ids",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column("pinned_message_id", sa.BigInteger(), nullable=True),
            sa.Column(
                "delivered_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["bot_id"], ["bots.id"],
                name=op.f("fk_bot_deliveries_bot_id"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_bot_deliveries")),
            sa.UniqueConstraint("bot_id", "user_id", name="uq_bot_delivery_user"),
        )
        # The UniqueConstraint ``uq_bot_delivery_user`` on ``(bot_id, user_id)``
        # creates a leading-prefix btree that already serves ``WHERE bot_id = ?``
        # lookups, so a separate single-column ``bot_id`` index is redundant.
        # (We have no ``WHERE user_id = ?``-only queries today either, so we
        # don't create one — the unique index is sufficient.)


def downgrade() -> None:
    if _table_exists("bot_deliveries"):
        op.drop_index(op.f("ix_bot_deliveries_user_id"), table_name="bot_deliveries")
        op.drop_index(op.f("ix_bot_deliveries_bot_id"), table_name="bot_deliveries")
        op.drop_table("bot_deliveries")
    if _column_exists("bots", "content_revision"):
        op.drop_column("bots", "content_revision")
    if _column_exists("bot_content_posts", "image_local_path"):
        op.drop_column("bot_content_posts", "image_local_path")
