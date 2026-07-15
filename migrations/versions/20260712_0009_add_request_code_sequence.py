"""add request_code_seq sequence for collision-free request codes

Request codes were minted as ``count(*) + 1049``. Two concurrent submits
computed the same count → the same ``REQ-<n>`` code → a unique-constraint
crash, and the counter walked backwards whenever a request was deleted. This
replaces it with a Postgres sequence (see request_repo.next_sequence), started
just above the highest existing code so no code is ever reissued.

Revision ID: 0009_add_request_code_sequence
Revises: 0008_widen_request_source_ref
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_request_code_sequence"
down_revision: str | None = "0008_widen_request_source_ref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Start one past the highest existing REQ-<n> so live codes are never reused.
    start = bind.execute(
        sa.text(
            "SELECT COALESCE(MAX(CAST(substring(code from 'REQ-([0-9]+)') AS INTEGER)), 1048) + 1 "
            "FROM requests"
        )
    ).scalar()
    start = int(start or 1049)
    op.execute("CREATE SEQUENCE IF NOT EXISTS request_code_seq MINVALUE 1")
    # is_called=false → the very next nextval() returns exactly ``start``.
    op.execute(sa.text("SELECT setval('request_code_seq', :n, false)").bindparams(n=start))


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS request_code_seq")
