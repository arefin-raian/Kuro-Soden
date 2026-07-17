"""Request repository."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import selectinload

try:
    # asyncpg surfaces a missing relation as this specific error; importing it
    # lets us self-heal ONLY that case and re-raise everything else untouched.
    from asyncpg.exceptions import UndefinedTableError
except ImportError:  # pragma: no cover - asyncpg absent (e.g. SQLite-only test env)
    class UndefinedTableError(Exception):  # type: ignore[no-redef]
        """Fallback when asyncpg isn't installed — never matches a real error."""

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

    # Idempotent create-and-seed for ``request_code_seq``. Runs as a single
    # atomic DO block so a fresh sequence starts just past the highest existing
    # ``REQ-<n>`` (never reissuing a live code) and an existing one is left
    # untouched. Postgres-only — SQLite has no CREATE SEQUENCE.
    _ENSURE_SEQ_SQL = text(
        """
        DO $$
        BEGIN
            IF to_regclass('request_code_seq') IS NULL THEN
                EXECUTE 'CREATE SEQUENCE request_code_seq MINVALUE 1';
                PERFORM setval(
                    'request_code_seq',
                    (SELECT COALESCE(
                        MAX(CAST(substring(code from 'REQ-([0-9]+)') AS INTEGER)),
                        1048) + 1
                     FROM requests),
                    false
                );
            END IF;
        END $$;
        """
    )

    async def next_sequence(self) -> int:
        """Monotonic request-code counter backed by a Postgres sequence.

        Was ``count(*) + 1049``, which two concurrent submits computed identically
        → duplicate ``code`` → unique-violation crash, and which walked backwards
        after any request was deleted. ``nextval`` is atomic and gap-tolerant.

        Self-healing: if the sequence is missing (a container booted before the
        migration/``create_all`` ran, or ``AUTO_CREATE_SCHEMA`` was off), the first
        ``nextval`` raises ``UndefinedTableError``. We catch that inside a SAVEPOINT
        so the outer request transaction survives, create+seed the sequence, then
        retry — so request intake can never be blocked by deploy ordering again.
        """
        try:
            async with self.session.begin_nested():
                result = await self.session.execute(
                    text("SELECT nextval('request_code_seq')")
                )
                return int(result.scalar_one())
        except DBAPIError as exc:
            # Only self-heal the "sequence doesn't exist yet" case; re-raise
            # anything else (connection loss, permissions) untouched.
            if not isinstance(getattr(exc, "orig", None), UndefinedTableError):
                raise
        # The SAVEPOINT rolled back cleanly; the sequence really is absent.
        await self.session.execute(self._ENSURE_SEQ_SQL)
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
