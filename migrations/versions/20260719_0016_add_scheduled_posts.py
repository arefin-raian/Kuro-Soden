"""add scheduled_posts table

Durable backing for deferred main-channel publishes. APScheduler jobs are
in-memory and their callables aren't serializable, so a restart would forget
pending schedules. This table is the source of truth: a 60s sweep publishes
past-due ``pending`` rows and marks them ``published``/``failed``. Times are
stored in UTC; each admin enters/reads them in their own timezone.

Revision ID: 0016_add_scheduled_posts
Revises: 0015_add_admin_timezone
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0016_add_scheduled_posts"
down_revision: str | None = "0015_add_admin_timezone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_posts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("request_code", sa.String(32), nullable=False),
        sa.Column("anime_title", sa.Text(), nullable=True),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("silent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("caption_override", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_posts")),
    )
    op.create_index(
        op.f("ix_scheduled_posts_request_code"),
        "scheduled_posts", ["request_code"],
    )
    op.create_index(
        op.f("ix_scheduled_posts_admin_telegram_id"),
        "scheduled_posts", ["admin_telegram_id"],
    )
    op.create_index(
        op.f("ix_scheduled_posts_scheduled_at"),
        "scheduled_posts", ["scheduled_at"],
    )
    op.create_index(
        op.f("ix_scheduled_posts_status"),
        "scheduled_posts", ["status"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduled_posts_status"), table_name="scheduled_posts")
    op.drop_index(op.f("ix_scheduled_posts_scheduled_at"), table_name="scheduled_posts")
    op.drop_index(op.f("ix_scheduled_posts_admin_telegram_id"), table_name="scheduled_posts")
    op.drop_index(op.f("ix_scheduled_posts_request_code"), table_name="scheduled_posts")
    op.drop_table("scheduled_posts")
