from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008_widen_request_source_ref"
down_revision: str | None = "0005_add_index_sections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``requests.source_ref`` was declared ``String(256)``, but the nyaa source
    # stores the full torrent metadata blob (title + torrent_url + view_url +
    # seeders + leechers + downloads + size_text + size_bytes + category_id +
    # trusted + dual_audio + audio + langs) via ``json.dumps(r)``. The serialized
    # blob exceeds 256 chars for any richly-described release (e.g. ``[Sokudo]
    # Akudama Drive (Uncensored) [1080p BD AV1][dual audio]`` ~ 440 chars).
    # asyncpg raises ``StringDataRightTruncationError`` and the silent UI failure
    # turns the admin's torrent click into a no-op. Widen to ``Text`` so we keep
    # lossless storage without redesigning ``nyaa._stub``/downstream readers.
    op.alter_column(
        "requests",
        "source_ref",
        existing_type=sa.String(256),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="source_ref::text",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Best-effort truncate so the ALTER succeeds on real data; rows whose
        # source_ref is currently ``None`` stay ``None`` and are unaffected.
        op.execute(
            "UPDATE requests SET source_ref = LEFT(source_ref, 256) "
            "WHERE source_ref IS NOT NULL AND length(source_ref) > 256"
        )
    op.alter_column(
        "requests",
        "source_ref",
        existing_type=sa.Text(),
        type_=sa.String(256),
        existing_nullable=True,
    )
