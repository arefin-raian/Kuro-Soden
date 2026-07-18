"""Management service — the admin-pool control plane behind Lelouch's Command.

Wraps the :class:`AdminAvailability` table with everything the ``lelouch|manage``,
``avail``, and ``hours`` surfaces need:

  • **Pool CRUD** — add/remove an admin, assign/unassign the bots (pipeline
    stages) they cover, weight them.
  • **Availability** — toggle on/off the field.
  • **Breaks** — schedule and clear time-boxed breaks.
  • **Working hours** — a UTC window the assignment engine + idle nudge honour.
  • **Reassignment** — move a stuck request's stage assignment to another admin.

All state lives in one row per admin, so the assignment engine
(:class:`AdminAssignmentEngine`) and this control plane read the same source of
truth. Methods return detached dataclass views so callers never touch a live
ORM object outside its session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from kurosoden.shared.admin_assignment import (
    AdminAssignment,
    AdminAvailability,
)

# The four pipeline stages an admin can be assigned to.
STAGES = ("lelouch", "levi", "senku", "gojo")


@dataclass
class AdminView:
    """Detached snapshot of one admin's management state."""

    telegram_id: int
    name: str | None
    is_available: bool
    assigned_bots: list[str]
    weight: int
    working_hours: dict | None
    on_break: bool
    break_until: str | None
    active_tasks: int
    total_completed: int


class ManagementService:
    """CRUD + control operations over the admin pool."""

    def __init__(self, sessionmaker):
        self._sm = sessionmaker

    def _maybe_session(self, _session=None):
        if _session is not None:
            from contextlib import nullcontext
            return nullcontext(_session)
        return self._sm()

    # ── Read ─────────────────────────────────────────────────────────────────

    async def _active_count(self, session, admin_id: int) -> int:
        return int((await session.execute(
            select(func.count(AdminAssignment.id)).where(
                AdminAssignment.admin_telegram_id == admin_id,
                AdminAssignment.status.in_(["assigned", "in_progress"]),
            )
        )).scalar() or 0)

    @staticmethod
    def _current_break(avail: AdminAvailability, now: datetime) -> str | None:
        """ISO end-time of the break covering ``now``, or None."""
        for b in (avail.scheduled_breaks or []):
            try:
                start = datetime.fromisoformat(b["start"])
                end = datetime.fromisoformat(b["end"])
            except (KeyError, ValueError, TypeError):
                continue
            if start <= now <= end:
                return end.isoformat()
        return None

    async def _view(self, session, a: AdminAvailability) -> AdminView:
        now = datetime.now(timezone.utc)
        brk = self._current_break(a, now)
        return AdminView(
            telegram_id=a.admin_telegram_id,
            name=a.admin_name,
            is_available=bool(a.is_available),
            assigned_bots=list(a.assigned_bots or []),
            weight=int(a.weight or 1),
            working_hours=a.working_hours,
            on_break=brk is not None,
            break_until=brk,
            active_tasks=await self._active_count(session, a.admin_telegram_id),
            total_completed=int(a.total_tasks_completed or 0),
        )

    async def list_admins(self, *, stage: str | None = None,
                          _session=None) -> list[AdminView]:
        """Every admin in the pool, optionally filtered to one stage."""
        async with self._maybe_session(_session) as session:
            rows = (await session.execute(
                select(AdminAvailability).order_by(AdminAvailability.created_at.asc())
            )).scalars().all()
            views = [await self._view(session, a) for a in rows]
        if stage:
            views = [v for v in views if stage in v.assigned_bots]
        return views

    async def get_admin(self, admin_id: int, *, _session=None) -> AdminView | None:
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                )
            )).scalar_one_or_none()
            return await self._view(session, a) if a else None

    # ── Pool CRUD ──────────────────────────────────────────────────────────────

    async def ensure_admin(self, admin_id: int, *, name: str | None = None,
                           _session=None) -> AdminView:
        """Get-or-create an admin row, refreshing the name if given."""
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                ).with_for_update()
            )).scalar_one_or_none()
            if a is None:
                a = AdminAvailability(
                    admin_telegram_id=admin_id,
                    admin_name=name,
                    is_available=True,
                    assigned_bots=[],
                    scheduled_breaks=[],
                    weight=1,
                )
                session.add(a)
            elif name and not a.admin_name:
                a.admin_name = name
            await session.flush()
            view = await self._view(session, a)
            if _session is None:
                await session.commit()
            return view

    async def remove_admin(self, admin_id: int, *, _session=None) -> bool:
        """Drop an admin from the pool entirely. Active assignments are left in
        place (they still reference the code) but the admin stops receiving new
        work — reassign first if the stuck task matters."""
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                )
            )).scalar_one_or_none()
            if a is None:
                return False
            await session.delete(a)
            if _session is None:
                await session.commit()
            return True

    async def set_bots(self, admin_id: int, bots: list[str], *,
                       _session=None) -> AdminView | None:
        """Replace the set of stages an admin covers (validated against STAGES)."""
        clean = [b for b in bots if b in STAGES]
        return await self._patch(admin_id, assigned_bots=clean, _session=_session)

    async def toggle_bot(self, admin_id: int, bot: str, *,
                         _session=None) -> AdminView | None:
        """Add the stage if absent, remove it if present."""
        if bot not in STAGES:
            return await self.get_admin(admin_id, _session=_session)
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                ).with_for_update()
            )).scalar_one_or_none()
            if a is None:
                return None
            current = list(a.assigned_bots or [])
            if bot in current:
                current.remove(bot)
            else:
                current.append(bot)
            a.assigned_bots = current
            await session.flush()
            view = await self._view(session, a)
            if _session is None:
                await session.commit()
            return view

    async def set_weight(self, admin_id: int, weight: int, *,
                         _session=None) -> AdminView | None:
        return await self._patch(admin_id, weight=max(1, min(int(weight), 10)),
                                 _session=_session)

    # ── Availability ────────────────────────────────────────────────────────────

    async def set_available(self, admin_id: int, available: bool, *,
                            _session=None) -> AdminView | None:
        return await self._patch(admin_id, is_available=bool(available),
                                 _session=_session)

    async def toggle_available(self, admin_id: int, *,
                               _session=None) -> AdminView | None:
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                ).with_for_update()
            )).scalar_one_or_none()
            if a is None:
                return None
            a.is_available = not a.is_available
            await session.flush()
            view = await self._view(session, a)
            if _session is None:
                await session.commit()
            return view

    # ── Breaks ──────────────────────────────────────────────────────────────────

    async def schedule_break(self, admin_id: int, *, hours: float = 1.0,
                             reason: str = "", start: datetime | None = None,
                             _session=None) -> AdminView | None:
        """Add a break window starting now (or ``start``) for ``hours`` hours."""
        start = start or datetime.now(timezone.utc)
        end = start + timedelta(hours=max(0.1, hours))
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                ).with_for_update()
            )).scalar_one_or_none()
            if a is None:
                return None
            breaks = list(a.scheduled_breaks or [])
            breaks.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "reason": reason or "break",
            })
            a.scheduled_breaks = breaks
            await session.flush()
            view = await self._view(session, a)
            if _session is None:
                await session.commit()
            return view

    async def clear_breaks(self, admin_id: int, *, _session=None) -> AdminView | None:
        """Wipe all breaks (return the admin to the field early)."""
        return await self._patch(admin_id, scheduled_breaks=[], _session=_session)

    # ── Working hours ─────────────────────────────────────────────────────────────

    async def set_hours(self, admin_id: int, start: int | None,
                        end: int | None, *, _session=None) -> AdminView | None:
        """Set (or clear, when either is None) the admin's UTC working window."""
        wh = None
        if start is not None and end is not None:
            wh = {"start": int(start) % 24, "end": int(end) % 24}
        return await self._patch(admin_id, working_hours=wh, _session=_session)

    # ── Reassignment ───────────────────────────────────────────────────────────

    async def reassign(self, request_code: str, stage: str, to_admin: int, *,
                       _session=None) -> bool:
        """Point a request's stage assignment at a different admin.

        Reopens the row under the new admin (status ``assigned``) so the target
        picks it up. Creates the assignment if none existed for that stage yet.
        """
        async with self._maybe_session(_session) as session:
            row = (await session.execute(
                select(AdminAssignment).where(
                    AdminAssignment.request_code == request_code,
                    AdminAssignment.stage == stage,
                    AdminAssignment.status.in_(["assigned", "in_progress"]),
                ).with_for_update()
            )).scalar_one_or_none()
            if row is None:
                row = AdminAssignment(
                    admin_telegram_id=to_admin,
                    request_code=request_code,
                    stage=stage,
                    status="assigned",
                )
                session.add(row)
            else:
                row.admin_telegram_id = to_admin
                row.status = "assigned"
            if _session is None:
                await session.commit()
            return True

    # ── Idle detection (used by the scheduled nudge) ─────────────────────────────

    async def idle_admins(self, stage: str | None = None, *,
                          _session=None) -> list[AdminView]:
        """Available, on-shift admins who currently hold zero active tasks.

        These are the candidates the idle-nudge job pings when work is waiting —
        anyone off-shift, on break, or already busy is left alone.
        """
        now = datetime.now(timezone.utc)
        out: list[AdminView] = []
        for v in await self.list_admins(stage=stage, _session=_session):
            if not v.is_available or v.on_break or v.active_tasks > 0:
                continue
            if v.working_hours:
                s = int(v.working_hours.get("start", 0)) % 24
                e = int(v.working_hours.get("end", 0)) % 24
                h = now.hour
                on = (s <= h < e) if s < e else (h >= s or h < e) if s != e else True
                if not on:
                    continue
            out.append(v)
        return out

    # ── Internal patch helper ─────────────────────────────────────────────────

    async def _patch(self, admin_id: int, *, _session=None, **fields) -> AdminView | None:
        async with self._maybe_session(_session) as session:
            a = (await session.execute(
                select(AdminAvailability).where(
                    AdminAvailability.admin_telegram_id == admin_id
                ).with_for_update()
            )).scalar_one_or_none()
            if a is None:
                return None
            for k, val in fields.items():
                setattr(a, k, val)
            await session.flush()
            view = await self._view(session, a)
            if _session is None:
                await session.commit()
            return view
