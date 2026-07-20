"""add per-admin timezone column

Each admin can enter/read scheduled-post times in their own IANA timezone
(e.g. "Asia/Dhaka"). NULL falls back to the global display timezone. This does
NOT touch ``working_hours`` (which stays UTC) — display/scheduling only.

Revision ID: 0015_add_admin_timezone
Revises: 0014_add_channel_broadcasts
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0015_add_admin_timezone"
down_revision: str | None = "0014_add_channel_broadcasts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_availability",
        sa.Column("timezone", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_availability", "timezone")
