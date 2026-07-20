"""add index_sections.repurposed flag

An admin can edit a reserved index slot into a normal post (removing its
"RESERVED FOR FUTURE" / "Slot N/N" marker). Once repurposed, auto-indexing must
never touch that slot again — not rebrand it, shift into it, or consume it. This
boolean records that decision durably so a restart doesn't forget it.

Revision ID: 0019_add_index_section_repurposed
Revises: 0018_add_bot_invite_link
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0019_add_index_section_repurposed"
down_revision: str | None = "0018_add_bot_invite_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "index_sections",
        sa.Column("repurposed", sa.Boolean(), server_default=sa.text("false"),
                  nullable=False),
    )


def downgrade() -> None:
    op.drop_column("index_sections", "repurposed")
