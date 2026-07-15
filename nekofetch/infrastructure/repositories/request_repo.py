"""Request repository."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from nekofetch.domain.enums import RequestStatus
from nekofetch.infrastructure.database.postgres.models import Request
from nekofetch.infrastructure.repositories.base import BaseRepository


class RequestRepository(BaseRepository[Request]):
    model = Request

    async def get_by_code(self, code: str) -> Request | None:
        # Eager-load the requester so cards can show a real name after the row is
        # detached/expunged (async SQLAlchemy can't lazy-load a detached relation).
        result = await self.session.execute(
            select(Request).where(Request.code == code).options(selectinload(Request.user))
        )
        return result.scalar_one_or_none()

    async def list_by_status(
        self, status: RequestStatus, *, limit: int = 50
    ) -> list[Request]:
        """Oldest-first requests in a given status (drives the review queue)."""
        result = await self.session.execute(
            select(Request)
            .where(Request.status == status)
            .order_by(Request.created_at.asc())
            .limit(limit)
            .options(selectinload(Request.user))
        )
        return list(result.scalars().all())

    async def list_for_user(self, user_id: int, *, limit: int = 20) -> list[Request]:
        result = await self.session.execute(
            select(Request)
            .where(Request.user_id == user_id)
            .order_by(Request.created_at.desc())
            .limit(limit)
            .options(selectinload(Request.user))
        )
        return list(result.scalars().all())

    async def next_sequence(self) -> int:
        """Monotonic request-code counter backed by a Postgres sequence.

        Was ``count(*) + 1049``, which two concurrent submits computed identically
        → duplicate ``code`` → unique-violation crash, and which walked backwards
        after any request was deleted. ``nextval`` is atomic and gap-tolerant.
        """
        result = await self.session.execute(text("SELECT nextval('request_code_seq')"))
        return int(result.scalar_one())

    async def pending_position(self, request_id: int) -> int:
        """1-based position of a request among those awaiting download."""
        active = {RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.QUEUED}
        result = await self.session.execute(
            select(Request.id)
            .where(Request.status.in_(active))
            .order_by(Request.created_at.asc())
        )
        ids = [row[0] for row in result.all()]
        return ids.index(request_id) + 1 if request_id in ids else 0
