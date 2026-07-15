"""add entry_id to storage_packs

Adds an ``entry_id`` column to the ``storage_packs`` table, which tracks the
AniList entry ID for per-extra identification. This enables the update-check
service to detect which specific OVA/MOVIE/ONA/SPECIAL entries have already
been published (previously all extras shared ``season=None`` and were
indistinguishable).

The unique constraint and index are updated to include ``entry_id`` so each
(anime, season, season_part, resolution, audio, entry_id) combo is unique.
Existing rows get ``entry_id = NULL`` and continue to work unchanged.

Revision ID: 0004_add_storage_pack_entry_id
Revises: 0003_add_bot_content_posts
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_add_storage_pack_entry_id"
# Re-parented onto the real branch-A head (0007). This migration originally
# forked off 0003, creating a second, never-applied head; the live DB walked
# branch A to 0007 and this column was silently missing. Chaining it after 0007
# folds the orphaned branch back into a single linear history.
down_revision: str | None = "0007_add_season_part"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: the fork meant this may run against a DB that already has some
    # of these objects (or none). Guard every step so it applies cleanly on the
    # live schema without exploding on "already exists" / "does not exist".
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("storage_packs")}
    uniques = {uc["name"] for uc in insp.get_unique_constraints("storage_packs")}
    indexes = {ix["name"] for ix in insp.get_indexes("storage_packs")}

    # Add the nullable column — existing rows get NULL, which is fine.
    if "entry_id" not in cols:
        op.add_column(
            "storage_packs",
            sa.Column("entry_id", sa.Integer(), nullable=True, index=True),
        )

    # Drop the old unique constraint and index, replace with entry_id-aware ones.
    if "uq_storage_pack" in uniques:
        op.drop_constraint("uq_storage_pack", "storage_packs", type_="unique")
    if "ix_storage_pack_lookup" in indexes:
        op.drop_index("ix_storage_pack_lookup", table_name="storage_packs")

    op.create_unique_constraint(
        "uq_storage_pack",
        "storage_packs",
        ["anime_doc_id", "season", "season_part", "resolution", "audio", "entry_id"],
    )
    op.create_index(
        "ix_storage_pack_lookup",
        "storage_packs",
        ["anime_doc_id", "season", "season_part", "resolution", "audio", "entry_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_storage_pack", "storage_packs", type_="unique")
    op.drop_index("ix_storage_pack_lookup", table_name="storage_packs")

    # Re-create the old constraints without entry_id.
    op.create_unique_constraint(
        "uq_storage_pack",
        "storage_packs",
        ["anime_doc_id", "season", "season_part", "resolution", "audio"],
    )
    op.create_index(
        "ix_storage_pack_lookup",
        "storage_packs",
        ["anime_doc_id", "season", "season_part", "resolution", "audio"],
    )

    op.drop_column("storage_packs", "entry_id")
