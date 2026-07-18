"""Tests for the admin-pool management control plane.

Covers:
  • ManagementService CRUD (ensure/remove, bots, weight)
  • Availability toggle + break scheduling/clearing
  • Working-hours set/clear
  • Reassignment (existing row + create-if-missing)
  • idle_admins filtering (availability / break / hours / load)
  • AdminAssignmentEngine honouring weight + working_hours in _find_best_admin
  • Lelouch voice builders render without error
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kurosoden.shared.management_service import ManagementService, STAGES


# ── CRUD ─────────────────────────────────────────────────────────────────────

class TestPoolCRUD:
    async def test_ensure_creates_then_gets(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        v = await svc.ensure_admin(500, name="Lelouch")
        assert v.telegram_id == 500
        assert v.name == "Lelouch"
        assert v.weight == 1
        assert v.assigned_bots == []
        # Idempotent get-or-create.
        again = await svc.ensure_admin(500)
        assert again.telegram_id == 500

    async def test_ensure_backfills_name(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(501)
        v = await svc.ensure_admin(501, name="Suzaku")
        assert v.name == "Suzaku"

    async def test_remove(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(502)
        assert await svc.remove_admin(502) is True
        assert await svc.get_admin(502) is None
        assert await svc.remove_admin(502) is False

    async def test_set_bots_filters_invalid(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(503)
        v = await svc.set_bots(503, ["levi", "bogus", "gojo"])
        assert set(v.assigned_bots) == {"levi", "gojo"}

    async def test_toggle_bot(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(504)
        v = await svc.toggle_bot(504, "senku")
        assert "senku" in v.assigned_bots
        v = await svc.toggle_bot(504, "senku")
        assert "senku" not in v.assigned_bots

    async def test_weight_clamped(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(505)
        assert (await svc.set_weight(505, 99)).weight == 10
        assert (await svc.set_weight(505, -5)).weight == 1


# ── Availability + breaks ──────────────────────────────────────────────────────

class TestAvailability:
    async def test_toggle_available(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(510)
        assert (await svc.toggle_available(510)).is_available is False
        assert (await svc.toggle_available(510)).is_available is True

    async def test_schedule_and_clear_break(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(511)
        v = await svc.schedule_break(511, hours=2.0, reason="lunch")
        assert v.on_break is True
        assert v.break_until is not None
        v = await svc.clear_breaks(511)
        assert v.on_break is False


# ── Working hours ──────────────────────────────────────────────────────────────

class TestWorkingHours:
    async def test_set_and_clear(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(520)
        v = await svc.set_hours(520, 8, 16)
        assert v.working_hours == {"start": 8, "end": 16}
        v = await svc.set_hours(520, None, None)
        assert v.working_hours is None

    async def test_wraps_modulo(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(521)
        v = await svc.set_hours(521, 22, 30)  # 30 % 24 == 6
        assert v.working_hours == {"start": 22, "end": 6}


# ── Reassignment ──────────────────────────────────────────────────────────────

class TestReassign:
    async def test_reassign_existing(self, sessionmaker, session):
        from kurosoden.shared.admin_assignment import AdminAssignment
        row = AdminAssignment(admin_telegram_id=600, request_code="REQ-9",
                              stage="levi", status="in_progress")
        session.add(row)
        await session.commit()

        svc = ManagementService(sessionmaker)
        assert await svc.reassign("REQ-9", "levi", 601) is True

        from sqlalchemy import select
        async with sessionmaker() as s:
            got = (await s.execute(select(AdminAssignment).where(
                AdminAssignment.request_code == "REQ-9"))).scalar_one()
            assert got.admin_telegram_id == 601
            assert got.status == "assigned"

    async def test_reassign_creates_when_missing(self, sessionmaker, session):
        from kurosoden.shared.admin_assignment import AdminAssignment
        from sqlalchemy import select
        svc = ManagementService(sessionmaker)
        assert await svc.reassign("REQ-NEW", "gojo", 700) is True
        async with sessionmaker() as s:
            got = (await s.execute(select(AdminAssignment).where(
                AdminAssignment.request_code == "REQ-NEW"))).scalar_one()
            assert got.admin_telegram_id == 700


# ── idle_admins filtering ──────────────────────────────────────────────────────

class TestIdleAdmins:
    async def test_only_available_idle_onshift(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        # ready, idle, always-on → included
        await svc.ensure_admin(800, name="Ready")
        await svc.set_bots(800, ["levi"])
        # off-duty → excluded
        await svc.ensure_admin(801, name="Off")
        await svc.set_bots(801, ["levi"])
        await svc.set_available(801, False)
        # on break → excluded
        await svc.ensure_admin(802, name="Break")
        await svc.set_bots(802, ["levi"])
        await svc.schedule_break(802, hours=1)

        idle = await svc.idle_admins(stage="levi")
        ids = {a.telegram_id for a in idle}
        assert 800 in ids
        assert 801 not in ids
        assert 802 not in ids

    async def test_offshift_excluded(self, sessionmaker, session):
        svc = ManagementService(sessionmaker)
        await svc.ensure_admin(810, name="Night")
        await svc.set_bots(810, ["levi"])
        now = datetime.now(timezone.utc)
        # A 1-hour window that does NOT contain the current hour.
        dead = (now.hour + 3) % 24
        await svc.set_hours(810, dead, (dead + 1) % 24)
        idle = await svc.idle_admins(stage="levi")
        assert 810 not in {a.telegram_id for a in idle}


# ── Engine routing honours weight + hours ──────────────────────────────────────

class TestEngineRouting:
    async def test_within_hours_helper(self):
        from kurosoden.shared.admin_assignment import (
            AdminAssignmentEngine, AdminAvailability)
        eng = AdminAssignmentEngine.__new__(AdminAssignmentEngine)
        base = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)  # 10:00
        # No window → always on.
        a = AdminAvailability(admin_telegram_id=1, working_hours=None)
        assert eng._within_hours(a, base) is True
        # In-window.
        a.working_hours = {"start": 8, "end": 16}
        assert eng._within_hours(a, base) is True
        # Out-of-window.
        a.working_hours = {"start": 16, "end": 20}
        assert eng._within_hours(a, base) is False
        # Wraps midnight (22→6): 10:00 is out; 02:00 is in.
        a.working_hours = {"start": 22, "end": 6}
        assert eng._within_hours(a, base) is False
        assert eng._within_hours(a, base.replace(hour=2)) is True

    async def test_weight_absorbs_more_load(self, sessionmaker, session):
        """A weight-2 admin with 1 active task outranks a weight-1 admin with 1."""
        from kurosoden.shared.admin_assignment import (
            AdminAssignmentEngine, AdminAssignment, AdminAvailability)
        # Two admins covering levi; both hold one active task.
        for tid, wt in ((900, 1), (901, 2)):
            session.add(AdminAvailability(
                admin_telegram_id=tid, admin_name=f"A{tid}", is_available=True,
                assigned_bots=["levi"], scheduled_breaks=[], weight=wt))
            session.add(AdminAssignment(admin_telegram_id=tid,
                                        request_code=f"REQ-{tid}", stage="levi",
                                        status="assigned"))
        await session.commit()

        engine = AdminAssignmentEngine(sessionmaker)
        async with sessionmaker() as s:
            best = await engine._find_best_admin(s, "levi")
        # weighted load: 900 → 1/1=1.0, 901 → 1/2=0.5 → 901 wins.
        assert best is not None
        assert best.admin_telegram_id == 901

    async def test_offshift_admin_skipped(self, sessionmaker, session):
        from kurosoden.shared.admin_assignment import (
            AdminAssignmentEngine, AdminAvailability)
        now = datetime.now(timezone.utc)
        dead = (now.hour + 4) % 24
        session.add(AdminAvailability(
            admin_telegram_id=910, admin_name="Night", is_available=True,
            assigned_bots=["levi"], scheduled_breaks=[], weight=1,
            working_hours={"start": dead, "end": (dead + 1) % 24}))
        await session.commit()
        engine = AdminAssignmentEngine(sessionmaker)
        async with sessionmaker() as s:
            best = await engine._find_best_admin(s, "levi")
        assert best is None


# ── Voice builders ─────────────────────────────────────────────────────────────

class TestVoice:
    def _view(self, **kw):
        from kurosoden.shared.management_service import AdminView
        base = dict(telegram_id=1, name="N", is_available=True, assigned_bots=["levi"],
                    weight=1, working_hours=None, on_break=False, break_until=None,
                    active_tasks=0, total_completed=0)
        base.update(kw)
        return AdminView(**base)

    def test_all_builders_render(self):
        from kurosoden.shared import lelouch_voice as V
        v = self._view()
        assert V.ICON in V.manage_roster([v])
        assert V.ICON in V.manage_roster([])  # empty pool
        assert V.ICON in V.manage_admin_detail(v)
        assert V.ICON in V.availability_board([v])
        assert V.ICON in V.availability_board([])
        assert V.ICON in V.hours_board([v], "normal")
        assert V.ICON in V.hours_board([], "paused")
        assert "1h" in V.break_scheduled("N", 1.0)
        assert "WRK-1" in V.reassigned("WRK-1", "N")
        assert V.stage_label("levi") == "Download"
