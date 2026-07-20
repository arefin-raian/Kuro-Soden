"""add bots.invite_link

A bot-minted **private** invite link (t.me/+…) to a distribution channel, used
by the main-channel Download button and the index hyperlink instead of the
public t.me/<username> link — so traffic flows through a link we control and can
revoke/replace on recreate. NULL for bots and for pre-existing channels.

Revision ID: 0018_add_bot_invite_link
Revises: 0017_add_channel_content_backups
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0018_add_bot_invite_link"
down_revision: str | None = "0017_add_channel_content_backups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("invite_link", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("bots", "invite_link")
