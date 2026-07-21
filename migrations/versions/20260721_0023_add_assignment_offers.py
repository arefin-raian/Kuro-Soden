"""add assignment offer/escalation columns

Phase 3 of the Lelouch/Levi routing work: assignments can now be direct duty,
one-hour offers, or closest-slot fallback duty. Existing rows stay active duty.

Revision ID: 0023_add_assignment_offers
Revises: 0022_add_admin_profile
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_add_assignment_offers"
down_revision: str | None = "0022_add_admin_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_assignments",
        sa.Column("assignment_mode", sa.String(16), nullable=False, server_default="duty"),
    )
    op.add_column(
        "admin_assignments",
        sa.Column("offer_attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("admin_assignments", sa.Column("offered_at", sa.DateTime(timezone=True)))
    op.add_column("admin_assignments", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("admin_assignments", sa.Column("responded_at", sa.DateTime(timezone=True)))
    op.add_column("admin_assignments", sa.Column("decision_reason", sa.String(64)))
    op.create_index(
        "uq_admin_assignments_open_request_stage",
        "admin_assignments",
        ["request_code", "stage"],
        unique=True,
        postgresql_where=sa.text("status IN ('assigned', 'in_progress', 'offered')"),
    )


def downgrade() -> None:
    op.drop_index("uq_admin_assignments_open_request_stage", table_name="admin_assignments")
    op.drop_column("admin_assignments", "decision_reason")
    op.drop_column("admin_assignments", "responded_at")
    op.drop_column("admin_assignments", "expires_at")
    op.drop_column("admin_assignments", "offered_at")
    op.drop_column("admin_assignments", "offer_attempt")
    op.drop_column("admin_assignments", "assignment_mode")
