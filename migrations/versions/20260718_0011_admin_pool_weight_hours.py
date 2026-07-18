"""admin pool tables + weight/working_hours

The admin-pool tables (``admin_availability`` / ``admin_assignments``) live in
``shared/admin_assignment.py``, outside the nekofetch models package, so they
were never captured by an Alembic migration — only by the dev-only
``create_all`` path. This revision brings them under migration control
idempotently (create-if-absent) and adds the two columns the management control
plane needs: per-admin assignment ``weight`` and a UTC ``working_hours`` window.

Revision ID: 0011_admin_pool_weight_hours
Revises: 0010_add_work_items
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_admin_pool_weight_hours"
down_revision: str | None = "0010_add_work_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "admin_assignments"):
        op.create_table(
            "admin_assignments",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("request_code", sa.String(length=32), nullable=False),
            sa.Column("stage", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False,
                      server_default="assigned"),
            sa.Column("task_count_at_assignment", sa.Integer(), nullable=True,
                      server_default="0"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_admin_assignments_admin_telegram_id",
                        "admin_assignments", ["admin_telegram_id"])
        op.create_index("ix_admin_assignments_request_code",
                        "admin_assignments", ["request_code"])

    if not _has_table(bind, "admin_availability"):
        op.create_table(
            "admin_availability",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("admin_name", sa.String(length=128), nullable=True),
            sa.Column("is_available", sa.Boolean(), nullable=False,
                      server_default=sa.true()),
            sa.Column("assigned_bots", postgresql.JSONB(), nullable=True),
            sa.Column("scheduled_breaks", postgresql.JSONB(), nullable=True),
            sa.Column("total_tasks_completed", sa.Integer(), nullable=True,
                      server_default="0"),
            sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("working_hours", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_admin_availability_admin_telegram_id",
                        "admin_availability", ["admin_telegram_id"], unique=True)
    else:
        # Table pre-existed (created by create_all) — add just the new columns.
        if not _has_column(bind, "admin_availability", "weight"):
            op.add_column("admin_availability",
                          sa.Column("weight", sa.Integer(), nullable=False,
                                    server_default="1"))
        if not _has_column(bind, "admin_availability", "working_hours"):
            op.add_column("admin_availability",
                          sa.Column("working_hours", postgresql.JSONB(),
                                    nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    # Only drop the columns this revision is responsible for adding; leave the
    # tables in place (they predate migration control).
    if _has_table(bind, "admin_availability"):
        if _has_column(bind, "admin_availability", "working_hours"):
            op.drop_column("admin_availability", "working_hours")
        if _has_column(bind, "admin_availability", "weight"):
            op.drop_column("admin_availability", "weight")
