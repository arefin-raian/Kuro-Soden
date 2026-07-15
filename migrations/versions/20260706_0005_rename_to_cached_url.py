"""rename bot_content_posts.image_local_path -> image_cached_url

When Session 5 shipped the bot-content image cache as a local file path under
``storage_path/bot_cards/``, the row column was named ``image_local_path`` —
true to its implementation but misleading about its purpose. Session 6 swaps
the cache backend to ``catbox.moe`` so the column now holds a public HTTPS URL
rather than a path on disk; the old name would silently invite bugs (any code
that wraps the value in ``pathlib.Path`` would treat the URL string as a
relative POSIX path and report ``False`` from ``.exists()``).

This migration renames the column to ``image_cached_url`` (generic, accurate).

Idempotency:
  * If ``image_cached_url`` already exists, skip.
  * If ``image_local_path`` exists, rename it.
  * Otherwise (fresh DB with ``auto_create_schema=True`` having already
    materialised the post-rename model), nothing to do.

Revision ID: 0005_rename_to_cached_url
Revises: 0004_distribution_rev_delivery
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_rename_to_cached_url"
down_revision: str | None = "0004_distribution_rev_delivery"
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
    if _column_exists("bot_content_posts", "image_cached_url"):
        return
    if _column_exists("bot_content_posts", "image_local_path"):
        op.alter_column(
            "bot_content_posts",
            "image_local_path",
            new_column_name="image_cached_url",
        )


def downgrade() -> None:
    if _column_exists("bot_content_posts", "image_cached_url") and not _column_exists(
        "bot_content_posts", "image_local_path"
    ):
        op.alter_column(
            "bot_content_posts",
            "image_cached_url",
            new_column_name="image_local_path",
        )
