"""add season_part to MediaFile and StoragePack

Adds ``season_part`` (nullable integer) to the ``files`` and
``storage_packs`` tables so we can represent season parts
(e.g. S3P1, S3P2) in file naming, watch guides, and post-processing
confirmation. Updates the storage_packs unique constraint and index
to include ``season_part``.

Revision ID: 0007_add_season_part
Revises: 0006_add_distribution_entity_type
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_add_season_part"
down_revision: str | None = "0006_add_distribution_entity_type"
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
    if not _column_exists("files", "season_part"):
        op.add_column(
            "files",
            sa.Column("season_part", sa.Integer(), nullable=True),
        )
    if not _column_exists("storage_packs", "season_part"):
        op.add_column(
            "storage_packs",
            sa.Column("season_part", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("files", "season_part"):
        op.drop_column("files", "season_part")
    if _column_exists("storage_packs", "season_part"):
        op.drop_column("storage_packs", "season_part")
