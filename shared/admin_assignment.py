"""Admin assignment engine — balanced workload distribution.

Each pipeline stage has a pool of admins. When a new task arrives, the engine
picks the best admin using these rules (in priority order):

    1. Prefer admins who are AVAILABLE (not on break, not unavailable).
    2. Prefer admins with ZERO current tasks.
    3. Among free admins, prefer the one who completed FEWER total tasks.
    4. Ignore admins marked as unavailable or on scheduled break.

Admin state is stored in a new ``admin_assignments`` table in PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from nekofetch.infrastructure.database.postgres.base import Base, PKMixin, TimestampMixin


# ── ORM Model ─────────────────────────────────────────────────────────────────

class AdminAssignment(Base, PKMixin, TimestampMixin):
    """Tracks which admin is assigned to which pipeline task."""

    __tablename__ = "admin_assignments"

    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    request_code: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    # "lelouch" | "levi" | "senku" | "gojo"
    status: Mapped[str] = mapped_column(String(16), default="assigned", nullable=False)
    # "assigned" | "in_progress" | "completed" | "rejected"
    task_count_at_assignment: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAvailability(Base, PKMixin, TimestampMixin):
    """Tracks admin availability, breaks, and bot assignments."""

    __tablename__ = "admin_availability"

    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    admin_name: Mapped[str | None] = mapped_column(String(128))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Which bots (pipeline stages) this admin works on.
    assigned_bots: Mapped[list[str] | None] = mapped_column(JSONB)
    # e.g. ["lelouch", "levi", "senku", "gojo"]
    # Scheduled breaks: list of {start, end, reason} dicts.
    scheduled_breaks: Mapped[list | None] = mapped_column(JSONB)
    total_tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    # Assignment weight: higher = more tasks routed here (a trusted admin can be
    # weighted up). Effective load is active_tasks / weight, so weight 2 lets an
    # admin carry twice the queue before they're passed over.
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Working window as {"start": 0-23, "end": 0-23} in UTC, or NULL for always-on.
    # Wraps past midnight when start > end (e.g. 22→6). Honoured by assignment +
    # the idle nudge so no one is roused off the clock.
    working_hours: Mapped[dict | None] = mapped_column(JSONB)


# ── Assignment Engine ─────────────────────────────────────────────────────────

@dataclass
class AssignmentResult:
    admin_telegram_id: int
    admin_name: str | None
    tasks_active: int
    tasks_completed: int


class AdminAssignmentEngine:
    """Picks the best admin for a pipeline task using balanced distribution."""

    def __init__(self, sessionmaker):
        self._sm = sessionmaker

    def _maybe_session(self, _session=None):
        """Context manager: yields ``_session`` if provided, else a new session."""
        if _session is not None:
            from contextlib import nullcontext
            return nullcontext(_session)
        return self._sm()

    async def assign(
        self,
        request_code: str,
        stage: str,
        *,
        preferred_admin: int | None = None,
        _session=None,
    ) -> AssignmentResult | None:
        """Assign a request to the best available admin for the given stage.

        Uses a single transaction with row-level locking to prevent races
        where two concurrent assigns pick the same admin.

        Args:
            request_code: The REQ-XXXX code to assign.
            stage: Pipeline stage ("lelouch" | "levi" | "senku" | "gojo").
            preferred_admin: Optional Telegram ID to force-assign to.
            _session: Optional existing session (caller manages transaction).

        Returns:
            AssignmentResult if an admin was found, None if no admin is available.
        """
        from sqlalchemy import func

        async with self._maybe_session(_session) as session:
            # Only begin a new transaction if we opened our own session.
            if _session is None:
                async with session.begin():
                    return await self._assign_impl(session, request_code, stage, preferred_admin)
            else:
                return await self._assign_impl(session, request_code, stage, preferred_admin)

    async def _assign_impl(self, session, request_code: str, stage: str,
                           preferred_admin: int | None):
        """Core assignment logic — caller manages the transaction."""
        from sqlalchemy import func

        # If a specific admin is forced and available, use them.
        if preferred_admin:
            avail = (
                await session.execute(
                    select(AdminAvailability).where(
                        AdminAvailability.admin_telegram_id == preferred_admin
                    ).with_for_update()
                )
            ).scalar_one_or_none()
            if avail and avail.is_available:
                return await self._create_assignment(
                    session, preferred_admin, request_code, stage, avail
                )
            # preferred_admin not found or unavailable — fall through to
            # the normal best-admin selection below.

        # Find the best admin for this stage.
        best = await self._find_best_admin(session, stage)
        if best is None:
            return None

        return await self._create_assignment(
            session, best.admin_telegram_id, request_code, stage, best
        )

    async def _find_best_admin(self, session, stage: str) -> AdminAvailability | None:
        """Find the best available admin for a stage using balanced strategy.

        Uses FOR UPDATE to lock the availability rows during the transaction.
        """
        from sqlalchemy import func

        # Get all admins assigned to this stage who are available.
        result = await session.execute(
            select(AdminAvailability).where(
                AdminAvailability.is_available.is_(True),
            ).with_for_update()
        )
        candidates = result.scalars().all()

        # Filter by stage assignment.
        stage_candidates = [
            a for a in candidates
            if a.assigned_bots and stage in a.assigned_bots
        ]
        if not stage_candidates:
            return None

        # Skip admins on scheduled break or off their working hours.
        now = datetime.now(timezone.utc)
        active_candidates = [
            a for a in stage_candidates
            if not self._is_on_break(a, now) and self._within_hours(a, now)
        ]
        if not active_candidates:
            return None

        # Count active tasks, then score by *weighted* load so a higher-weighted
        # admin absorbs more of the queue before being passed over.
        scored: list[tuple[float, int, AdminAvailability]] = []
        for a in active_candidates:
            active_count = (
                await session.execute(
                    select(func.count(AdminAssignment.id)).where(
                        AdminAssignment.admin_telegram_id == a.admin_telegram_id,
                        AdminAssignment.status.in_(["assigned", "in_progress"]),
                    )
                )
            ).scalar() or 0
            weight = max(1, a.weight or 1)
            scored.append((active_count / weight, a.total_tasks_completed, a))

        # Sort: lowest weighted load first, then fewest total completed.
        scored.sort(key=lambda x: (x[0], x[1]))
        return scored[0][2]

    @staticmethod
    def _is_on_break(avail: AdminAvailability, now: datetime) -> bool:
        """Check if an admin is currently on a scheduled break."""
        if not avail.scheduled_breaks:
            return False
        for b in avail.scheduled_breaks:
            try:
                start = datetime.fromisoformat(b["start"])
                end = datetime.fromisoformat(b["end"])
                if start <= now <= end:
                    return True
            except (KeyError, ValueError, TypeError):
                continue
        return False

    @staticmethod
    def _within_hours(avail: AdminAvailability, now: datetime) -> bool:
        """True when ``now`` (UTC) falls in the admin's working window.

        No window set ⇒ always on. A window that wraps midnight (start > end,
        e.g. 22→6) is treated as spanning the boundary.
        """
        wh = avail.working_hours
        if not wh:
            return True
        try:
            start = int(wh["start"]) % 24
            end = int(wh["end"]) % 24
        except (KeyError, ValueError, TypeError):
            return True
        hour = now.hour
        if start == end:
            return True  # degenerate/full-day window
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end  # wraps midnight

    async def _create_assignment(
        self, session, admin_id: int, request_code: str, stage: str, avail: AdminAvailability
    ) -> AssignmentResult:
        """Persist an assignment and return the result."""
        from sqlalchemy import func

        active_count = (
            await session.execute(
                select(func.count(AdminAssignment.id)).where(
                    AdminAssignment.admin_telegram_id == admin_id,
                    AdminAssignment.status.in_(["assigned", "in_progress"]),
                )
            )
        ).scalar() or 0

        assignment = AdminAssignment(
            admin_telegram_id=admin_id,
            request_code=request_code,
            stage=stage,
            status="assigned",
            task_count_at_assignment=active_count,
        )
        session.add(assignment)
        await session.flush()

        return AssignmentResult(
            admin_telegram_id=admin_id,
            admin_name=avail.admin_name,
            tasks_active=active_count + 1,
            tasks_completed=avail.total_tasks_completed,
        )

    async def complete_task(self, request_code: str, stage: str,
                            _session=None) -> None:
        """Mark a task as completed and increment the admin's counter."""
        async with self._maybe_session(_session) as session:
            assignment = (
                await session.execute(
                    select(AdminAssignment).where(
                        AdminAssignment.request_code == request_code,
                        AdminAssignment.stage == stage,
                        AdminAssignment.status == "assigned",
                    )
                )
            ).scalar_one_or_none()
            if assignment is None:
                return
            assignment.status = "completed"
            assignment.completed_at = datetime.now(timezone.utc)

            # Atomic increment — a Python read-then-write loses counts
            # when two admins complete tasks concurrently.
            from sqlalchemy import update

            await session.execute(
                update(AdminAvailability)
                .where(AdminAvailability.admin_telegram_id == assignment.admin_telegram_id)
                .values(total_tasks_completed=AdminAvailability.total_tasks_completed + 1)
            )

            await session.commit()

    async def get_active_tasks(self, admin_telegram_id: int,
                                _session=None) -> list[AdminAssignment]:
        """Get all active tasks for an admin."""
        async with self._maybe_session(_session) as session:
            result = await session.execute(
                select(AdminAssignment).where(
                    AdminAssignment.admin_telegram_id == admin_telegram_id,
                    AdminAssignment.status.in_(["assigned", "in_progress"]),
                ).order_by(AdminAssignment.created_at.asc())
            )
            return list(result.scalars().all())
