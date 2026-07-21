"""add admin profile columns (country, hours cap, weekday/weekend slots)

Phase 2 of the Lelouch/Levi rework: admins gain a self-service profile so the
slot-aware assignment engine (Phase 3) can route work to the right person at the
right local time. All columns are nullable and additive — existing admin rows
keep working (NULL = no profile set yet). The self-heal reconciler in
``session.py`` also adds these on boot, but the migration is authoritative.

Revision ID: 0022_add_admin_profile
Revises: 0021_add_backup_imgbb_url
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022_add_admin_profile"
down_revision: str | None = "0021_add_backup_imgbb_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admin_availability", sa.Column("country", sa.String(64), nullable=True))
    op.add_column(
        "admin_availability",
        sa.Column("max_hours_per_day", sa.Integer(), nullable=True),
    )
    op.add_column("admin_availability", sa.Column("slots_weekday", JSONB(), nullable=True))
    op.add_column("admin_availability", sa.Column("slots_weekend", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("admin_availability", "slots_weekend")
    op.drop_column("admin_availability", "slots_weekday")
    op.drop_column("admin_availability", "max_hours_per_day")
    op.drop_column("admin_availability", "country")
