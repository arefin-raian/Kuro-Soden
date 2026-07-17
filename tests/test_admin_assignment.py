"""Tests for kurosoden/shared/admin_assignment.py — Admin assignment engine.

Covers:
  • AssignmentResult dataclass defaults
  • AdminAssignment / AdminAvailability ORM models
  • AdminAssignmentEngine._is_on_break() edge cases
  • AdminAssignmentEngine.assign() with DB
  • AdminAssignmentEngine.complete_task()
  • AdminAssignmentEngine.get_active_tasks()
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# AssignmentResult dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssignmentResult:
    """Pure data class — no DB needed."""

    def test_constructor_all_fields(self):
        from kurosoden.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(
            admin_telegram_id=123,
            admin_name="Alice",
            tasks_active=3,
            tasks_completed=42,
        )
        assert r.admin_telegram_id == 123
        assert r.admin_name == "Alice"
        assert r.tasks_active == 3
        assert r.tasks_completed == 42

    def test_none_admin_name(self):
        from kurosoden.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name=None, tasks_active=0, tasks_completed=0)
        assert r.admin_name is None

    def test_zero_tasks(self):
        from kurosoden.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name="New Admin", tasks_active=0, tasks_completed=0)
        assert r.tasks_active == 0
        assert r.tasks_completed == 0

    def test_high_tasks(self):
        from kurosoden.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name="Veteran", tasks_active=50, tasks_completed=9999)
        assert r.tasks_completed == 9999


# ═══════════════════════════════════════════════════════════════════════════════
# ORM Model field validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminAssignmentModel:
    """ORM model field defaults and constraints."""

    def test_tablename(self):
        from kurosoden.shared.admin_assignment import AdminAssignment
        assert AdminAssignment.__tablename__ == "admin_assignments"

    async def test_default_status(self, session):
        from kurosoden.shared.admin_assignment import AdminAssignment
        a = AdminAssignment(admin_telegram_id=1, request_code="REQ-1", stage="levi")
        session.add(a)
        await session.flush()
        assert a.status == "assigned"

    async def test_default_task_count(self, session):
        from kurosoden.shared.admin_assignment import AdminAssignment
        a = AdminAssignment(admin_telegram_id=1, request_code="REQ-1", stage="levi")
        session.add(a)
        await session.flush()
        assert a.task_count_at_assignment == 0

    def test_completed_at_none_by_default(self):
        from kurosoden.shared.admin_assignment import AdminAssignment
        a = AdminAssignment(admin_telegram_id=1, request_code="REQ-1", stage="levi")
        assert a.completed_at is None

    async def test_stage_persistence(self, session):
        from kurosoden.shared.admin_assignment import AdminAssignment
        a = AdminAssignment(admin_telegram_id=999, request_code="REQ-STAGE", stage="senku", status="assigned")
        session.add(a)
        await session.flush()
        assert a.id is not None
        assert a.stage == "senku"


class TestAdminAvailabilityModel:
    """ORM model for admin availability."""

    def test_tablename(self):
        from kurosoden.shared.admin_assignment import AdminAvailability
        assert AdminAvailability.__tablename__ == "admin_availability"

    async def test_default_is_available(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        a = AdminAvailability(admin_telegram_id=1)
        session.add(a)
        await session.flush()
        assert a.is_available is True

    async def test_default_total_tasks(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        a = AdminAvailability(admin_telegram_id=1)
        session.add(a)
        await session.flush()
        assert a.total_tasks_completed == 0

    async def test_assigned_bots_default(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        a = AdminAvailability(
            admin_telegram_id=200,
            admin_name="Bob",
            assigned_bots=["lelouch", "levi"],
        )
        session.add(a)
        await session.flush()
        assert a.assigned_bots == ["lelouch", "levi"]

    async def test_scheduled_breaks_json(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        breaks = [
            {"start": "2026-01-01T00:00:00+00:00", "end": "2026-01-02T00:00:00+00:00", "reason": "vacation"},
        ]
        a = AdminAvailability(admin_telegram_id=300, admin_name="Charlie", scheduled_breaks=breaks)
        session.add(a)
        await session.flush()
        assert len(a.scheduled_breaks) == 1
        assert a.scheduled_breaks[0]["reason"] == "vacation"

    async def test_unique_telegram_id_constraint(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        a1 = AdminAvailability(admin_telegram_id=400, admin_name="Dave")
        session.add(a1)
        await session.flush()

        a2 = AdminAvailability(admin_telegram_id=400, admin_name="Dave Duplicate")
        session.add(a2)
        with pytest.raises(Exception):
            await session.flush()

    async def test_null_admin_name_is_ok(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        a = AdminAvailability(admin_telegram_id=500, admin_name=None)
        session.add(a)
        await session.flush()
        assert a.admin_name is None


# ═══════════════════════════════════════════════════════════════════════════════
# AdminAssignmentEngine._is_on_break — static method, no DB needed
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsOnBreak:
    """Comprehensive edge cases for scheduled break detection."""

    @pytest.fixture
    def engine(self, sessionmaker):
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine
        return AdminAssignmentEngine(sessionmaker)

    @pytest.fixture
    def _avail(self, session):
        from kurosoden.shared.admin_assignment import AdminAvailability
        return lambda breaks=None: AdminAvailability(
            admin_telegram_id=1, admin_name="Test", scheduled_breaks=breaks
        )

    def test_no_breaks(self, engine, _avail):
        a = _avail(None)
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_empty_breaks_list(self, engine, _avail):
        a = _avail([])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_active_break(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": (now - timedelta(hours=1)).isoformat(),
             "end": (now + timedelta(hours=1)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is True

    def test_expired_break(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": (now - timedelta(days=2)).isoformat(),
             "end": (now - timedelta(days=1)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is False

    def test_future_break(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": (now + timedelta(days=1)).isoformat(),
             "end": (now + timedelta(days=2)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is False

    def test_boundary_start_exact(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": now.isoformat(), "end": (now + timedelta(hours=2)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is True

    def test_boundary_end_exact(self, engine, _avail):
        end = datetime.now(timezone.utc)
        a = _avail([
            {"start": (end - timedelta(hours=2)).isoformat(), "end": end.isoformat()},
        ])
        assert engine._is_on_break(a, end) is True

    def test_multiple_breaks_one_active(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": (now - timedelta(days=10)).isoformat(), "end": (now - timedelta(days=8)).isoformat()},
            {"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
            {"start": (now + timedelta(days=5)).isoformat(), "end": (now + timedelta(days=7)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is True

    def test_invalid_break_missing_start(self, engine, _avail):
        a = _avail([{"end": "2026-01-01T00:00:00+00:00"}])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_invalid_break_missing_end(self, engine, _avail):
        a = _avail([{"start": "2026-01-01T00:00:00+00:00"}])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_invalid_break_bad_iso(self, engine, _avail):
        a = _avail([{"start": "not-a-date", "end": "also-not-a-date"}])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_mixed_valid_invalid_breaks(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": "invalid", "end": "also-invalid"},
            {"start": (now - timedelta(hours=1)).isoformat(), "end": (now + timedelta(hours=1)).isoformat()},
        ])
        # The second break is active, so should return True.
        assert engine._is_on_break(a, now) is True

    def test_break_with_timezone_offset(self, engine, _avail):
        now = datetime.now(timezone.utc)
        a = _avail([
            {"start": (now - timedelta(hours=2)).isoformat(),
             "end": (now + timedelta(hours=2)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is True


# ═══════════════════════════════════════════════════════════════════════════════
# AdminAssignmentEngine — DB integration tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminAssignmentEngineDB:
    """Tests that need the SQLite in-memory database."""

    @pytest.fixture
    def engine(self, sessionmaker):
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine
        return AdminAssignmentEngine(sessionmaker)

    # ── assign() ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_assign_successful(self, engine, session, admin_availability):
        result = await engine.assign("REQ-NEW", "levi")
        assert result is not None
        assert result.admin_telegram_id == 100
        assert result.tasks_active >= 1

    @pytest.mark.asyncio
    async def test_assign_no_available_admins(self, engine, session):
        """Should return None when no admins are available for the stage."""
        result = await engine.assign("REQ-X", "gojo")
        assert result is None

    @pytest.mark.asyncio
    async def test_assign_with_preferred_admin(self, engine, session, admin_availability):
        from kurosoden.tests.helpers import _create_admin_availability
        # Add a second admin.
        await _create_admin_availability(session, admin_telegram_id=200, admin_name="Admin2")
        result = await engine.assign("REQ-PREF", "levi", preferred_admin=200)
        assert result is not None
        assert result.admin_telegram_id == 200

    @pytest.mark.asyncio
    async def test_preferred_admin_ignored_if_unavailable(self, engine, session, admin_availability):
        result = await engine.assign("REQ-Y", "levi", preferred_admin=999)  # Doesn't exist
        # Should fall back to available admin.
        assert result is not None
        assert result.admin_telegram_id == 100

    @pytest.mark.asyncio
    async def test_assign_prefers_fewer_active_tasks(self, engine, session, admin_availability):
        from kurosoden.tests.helpers import _create_admin_availability
        # Admin 200: 0 active tasks, 50 completed.
        await _create_admin_availability(session, admin_telegram_id=200, admin_name="LessBusy", total_tasks_completed=50)
        # Admin 100 (default): 0 active, 0 completed.
        result = await engine.assign("REQ-BAL", "levi")
        # Both have 0 active. Admin 100 has fewer completed → should be chosen.
        assert result.admin_telegram_id == 100

    @pytest.mark.asyncio
    async def test_assign_skips_unavailable_admin(self, engine, session, admin_availability):
        from kurosoden.tests.helpers import _create_admin_availability
        await _create_admin_availability(session, admin_telegram_id=200, admin_name="Unavailable", is_available=False)
        result = await engine.assign("REQ-SKIP", "levi")
        # Admin 100 is the only available one.
        assert result.admin_telegram_id == 100

    @pytest.mark.asyncio
    async def test_assign_skips_admin_on_break(self, engine, session, admin_availability):
        from kurosoden.tests.helpers import _create_admin_availability
        now = datetime.now(timezone.utc)
        breaks = [
            {"start": (now - timedelta(hours=1)).isoformat(),
             "end": (now + timedelta(hours=1)).isoformat()},
        ]
        # Admin 200 is on break now.
        await _create_admin_availability(session, admin_telegram_id=200, admin_name="OnBreak", scheduled_breaks=breaks)
        result = await engine.assign("REQ-BREAK", "levi")
        # Only Admin 100 should be available.
        assert result is not None
        assert result.admin_telegram_id == 100

    @pytest.mark.asyncio
    async def test_assign_filter_by_stage(self, engine, session, admin_availability):
        from kurosoden.tests.helpers import _create_admin_availability
        # Admin 200: only on senku + gojo.
        await _create_admin_availability(session, admin_telegram_id=200, admin_name="SenkuAdmin", assigned_bots=["senku", "gojo"])
        result = await engine.assign("REQ-STAGE", "levi")
        # Admin 100 is on all stages including levi.
        assert result.admin_telegram_id == 100

    @pytest.mark.asyncio
    async def test_assign_creates_db_row(self, engine, session, admin_availability):
        from sqlalchemy import select
        from kurosoden.shared.admin_assignment import AdminAssignment

        await engine.assign("REQ-DB", "levi")
        result = await session.execute(
            select(AdminAssignment).where(AdminAssignment.request_code == "REQ-DB")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.stage == "levi"
        assert row.status == "assigned"
        assert row.admin_telegram_id == 100

    # ── complete_task() ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_complete_task_success(self, engine, session, admin_assignment, admin_availability):
        await engine.complete_task("REQ-0001", "levi")
        # The engine commits its own session; refresh to see the change.
        await session.refresh(admin_assignment)
        assert admin_assignment.status == "completed"
        assert admin_assignment.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_task_increments_counter(self, engine, session, admin_assignment, admin_availability):
        from sqlalchemy import select
        from kurosoden.shared.admin_assignment import AdminAvailability

        prev = admin_availability.total_tasks_completed
        await engine.complete_task("REQ-0001", "levi")
        await session.refresh(admin_availability)
        assert admin_availability.total_tasks_completed == prev + 1

    @pytest.mark.asyncio
    async def test_complete_task_non_existent(self, engine, session):
        """Should not crash when assignment doesn't exist."""
        await engine.complete_task("REQ-NOPE", "levi")  # No error expected.

    @pytest.mark.asyncio
    async def test_complete_task_only_assigned_status(self, engine, session, admin_assignment):
        """Only 'assigned' status rows should be completed."""
        admin_assignment.status = "completed"
        await engine.complete_task("REQ-0001", "levi")
        # Should have been skipped (WHERE status='assigned').
        from sqlalchemy import select
        from kurosoden.shared.admin_assignment import AdminAssignment
        result = await session.execute(
            select(AdminAssignment).where(AdminAssignment.request_code == "REQ-0001")
        )
        row = result.scalar_one()
        # Status unchanged (was already "completed", query didn't match).
        assert row.status == "completed"

    # ── get_active_tasks() ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_active_tasks_finds_assigned(self, engine, session, admin_assignment):
        tasks = await engine.get_active_tasks(100)
        assert len(tasks) >= 1
        assert tasks[0].request_code == "REQ-0001"

    @pytest.mark.asyncio
    async def test_get_active_tasks_empty(self, engine, session):
        tasks = await engine.get_active_tasks(999)
        assert tasks == []

    @pytest.mark.asyncio
    async def test_get_active_tasks_excludes_completed(self, engine, session, admin_assignment):
        admin_assignment.status = "completed"
        await session.commit()  # Persist so the engine's own session can see it.
        tasks = await engine.get_active_tasks(100)
        assert all(t.request_code != "REQ-0001" for t in tasks)

    @pytest.mark.asyncio
    async def test_get_active_tasks_includes_in_progress(self, engine, session, admin_assignment):
        admin_assignment.status = "in_progress"
        tasks = await engine.get_active_tasks(100)
        assert any(t.request_code == "REQ-0001" for t in tasks)

    @pytest.mark.asyncio
    async def test_get_active_tasks_ordered_by_created_at(self, engine, session):
        from kurosoden.tests.helpers import _create_admin_assignment, _create_admin_availability
        await _create_admin_availability(session, admin_telegram_id=700)
        await _create_admin_assignment(session, admin_telegram_id=700, request_code="REQ-A", status="assigned")
        await _create_admin_assignment(session, admin_telegram_id=700, request_code="REQ-B", status="assigned")
        await _create_admin_assignment(session, admin_telegram_id=700, request_code="REQ-C", status="assigned")
        tasks = await engine.get_active_tasks(700)
        codes = [t.request_code for t in tasks]
        assert codes == ["REQ-A", "REQ-B", "REQ-C"]
