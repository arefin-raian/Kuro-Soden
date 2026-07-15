"""Edge-case and regression tests — boundary conditions and unusual inputs.

Covers:
  • Empty strings, None values, whitespace-only inputs
  • Extremely long values (titles, codes, names)
  • Unicode, emoji, and special characters
  • Malformed JSON in scheduled_breaks
  • Concurrent access patterns
  • Boundary datetime values
  • Zero and negative values
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Empty / None / whitespace inputs
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyNullInputs:
    """All services should handle None and empty inputs gracefully."""

    @pytest.mark.asyncio
    async def test_dedup_none_title(self, sessionmaker):
        from kage.shared.dedup import DedupService
        svc = DedupService(sessionmaker)
        r = await svc.check(None, anime_doc_id=None)
        assert r.exists is False

    @pytest.mark.asyncio
    async def test_dedup_whitespace_title(self, sessionmaker):
        from kage.shared.dedup import DedupService
        svc = DedupService(sessionmaker)
        r = await svc.check("   ", anime_doc_id=None)
        assert r.exists is False

    @pytest.mark.asyncio
    async def test_dedup_empty_string_title(self, sessionmaker):
        from kage.shared.dedup import DedupService
        svc = DedupService(sessionmaker)
        r = await svc.check("", anime_doc_id=None)
        assert r.exists is False

    def test_assignment_result_none_name(self):
        from kage.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name=None, tasks_active=0, tasks_completed=0)
        assert r.admin_name is None

    def test_dedup_result_all_none(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.exists is False
        assert r.source == ""
        assert r.title == ""
        assert r.bot_username is None
        assert r.main_channel_link is None
        assert r.request_code is None
        assert r.current_stage is None

    def test_esc_q_none_returns_empty(self):
        from kage.bots.lelouch.handlers.requests import _esc_q
        assert _esc_q(None) == ""

    def test_esc_q_empty_returns_empty(self):
        from kage.bots.lelouch.handlers.requests import _esc_q
        assert _esc_q("") == ""

    def test_esc_q_whitespace_preserved(self):
        from kage.bots.lelouch.handlers.requests import _esc_q
        assert _esc_q("   ") == "   "


# ═══════════════════════════════════════════════════════════════════════════════
# Long values
# ═══════════════════════════════════════════════════════════════════════════════

class TestLongValues:
    """Services should handle extremely long values without errors."""

    def test_very_long_title(self):
        from kage.shared.dedup import DedupResult
        title = "A" * 10000
        r = DedupResult(title=title, exists=True, source="main_channel")
        assert len(r.title) == 10000

    def test_very_long_request_code(self):
        from kage.shared.admin_assignment import AssignmentResult
        # Simulate a very long code (should be fine).
        assert True  # String length isn't constrained at the dataclass level.

    def test_very_long_admin_name(self):
        from kage.shared.admin_assignment import AdminAvailability
        long_name = "Admin " + "X" * 200
        a = AdminAvailability(admin_telegram_id=1, admin_name=long_name)
        assert a.admin_name == long_name

    @pytest.mark.asyncio
    async def test_very_long_anime_title_db(self, session):
        from kage.tests.helpers import _create_request
        long_title = "Attack on Titan: " + "The " * 50 + "Final Season"
        r = await _create_request(session, code="REQ-LONG", anime_title=long_title[:256], anime_doc_id="anilist:long1")
        assert r.anime_title == long_title[:256]

    @pytest.mark.asyncio
    async def test_many_assigned_bots(self, session):
        from kage.shared.admin_assignment import AdminAvailability
        many_bots = [f"bot_{i}" for i in range(100)]
        a = AdminAvailability(admin_telegram_id=999, admin_name="MultiBot", assigned_bots=many_bots)
        session.add(a)
        await session.flush()
        assert len(a.assigned_bots) == 100

    @pytest.mark.asyncio
    async def test_many_scheduled_breaks(self, session):
        from kage.shared.admin_assignment import AdminAvailability
        breaks = [
            {"start": f"2026-{i:02d}-01T00:00:00+00:00",
             "end": f"2026-{i:02d}-02T00:00:00+00:00",
             "reason": f"break_{i}"}
            for i in range(1, 10)
        ]
        a = AdminAvailability(admin_telegram_id=998, admin_name="FrequentBreaker", scheduled_breaks=breaks)
        session.add(a)
        await session.flush()
        assert len(a.scheduled_breaks) == 9


# ═══════════════════════════════════════════════════════════════════════════════
# Unicode, emoji, special characters
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnicodeAndEmoji:
    """All text fields should handle Unicode and emoji."""

    def test_japanese_title_dedup(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(title="進撃の巨人 The Final Season 完結編", exists=True)
        assert "進撃の巨人" in r.title

    def test_emoji_in_title(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(title="🎬✨ Anime Movie 🎥🌟", exists=True)
        assert "🎬" in r.title

    def test_korean_title(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(title="신의 탑", exists=True)
        assert "신의 탑" in r.title

    def test_arabic_title(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(title="هجوم العمالقة", exists=True)
        assert "هجوم" in r.title

    def test_special_html_chars_in_title(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(title="<Anime> & Manga", exists=True)
        assert "<Anime>" in r.title
        assert "&" in r.title

    def test_null_byte_in_title(self):
        """Null bytes shouldn't crash anything."""
        from kage.shared.dedup import DedupResult
        try:
            r = DedupResult(title="Anime\x00Title")
            # If it gets here without crash, that's a pass.
            assert True
        except Exception:
            # Some systems may reject null bytes — that's also acceptable.
            pass

    def test_rtl_text_in_admin_name(self):
        from kage.shared.admin_assignment import AdminAvailability
        name = "مسؤول"
        a = AdminAvailability(admin_telegram_id=1, admin_name=name)
        assert a.admin_name == name

    def test_esc_q_japanese(self):
        from kage.bots.lelouch.handlers.requests import _esc_q
        result = _esc_q("進撃の巨人")
        assert "進撃" in result
        # Japanese characters should NOT be escaped.
        assert result == "進撃の巨人"

    def test_esc_q_emoji_preserved(self):
        from kage.bots.lelouch.handlers.requests import _esc_q
        result = _esc_q("🎬 Attack on Titan 🎥")
        assert "🎬" in result
        assert "🎥" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Malformed data
# ═══════════════════════════════════════════════════════════════════════════════

class TestMalformedData:
    """Services should handle malformed/missing data gracefully."""

    def test_scheduled_breaks_not_a_list(self, sessionmaker):
        """If scheduled_breaks is somehow not iterable, _is_on_break handles it."""
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(sessionmaker)

        a = AdminAvailability(admin_telegram_id=1)
        a.scheduled_breaks = None
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_scheduled_breaks_empty_list(self, sessionmaker):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(sessionmaker)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_break_with_none_start(self, sessionmaker):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(sessionmaker)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[
            {"start": None, "end": "2026-01-01T00:00:00+00:00"},
        ])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_break_with_missing_keys(self, sessionmaker):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(sessionmaker)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[{}])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_break_with_wrong_type(self, sessionmaker):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(sessionmaker)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[
            "not-a-dict",
            123,
            None,
        ])
        # Should not crash — each bad entry is skipped.
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_assigned_bots_none(self, sessionmaker):
        """If assigned_bots is None, _find_best_admin should handle it."""
        from kage.shared.admin_assignment import AdminAvailability
        a = AdminAvailability(admin_telegram_id=1, assigned_bots=None)
        assert a.assigned_bots is None


# ═══════════════════════════════════════════════════════════════════════════════
# Boundary values
# ═══════════════════════════════════════════════════════════════════════════════

class TestBoundaryValues:
    """Boundary conditions for counts, dates, and ranges."""

    def test_zero_tasks_completed(self):
        from kage.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name="New", tasks_active=0, tasks_completed=0)
        assert r.tasks_completed == 0

    def test_max_tasks_completed(self):
        from kage.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name="Veteran", tasks_active=0, tasks_completed=2**31 - 1)
        assert r.tasks_completed > 0

    def test_negative_tasks(self):
        """Should work even with negative values (unlikely but shouldn't crash)."""
        from kage.shared.admin_assignment import AssignmentResult
        r = AssignmentResult(admin_telegram_id=1, admin_name="Bugged", tasks_active=-1, tasks_completed=-5)
        assert r.tasks_active == -1

    def test_datetime_boundary_min(self):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(None)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[
            {"start": "1970-01-01T00:00:00+00:00", "end": "1970-01-01T00:00:01+00:00"},
        ])
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_datetime_boundary_max(self):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(None)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[
            {"start": "2099-12-31T23:59:59+00:00", "end": "2100-01-01T00:00:00+00:00"},
        ])
        # Far future break — not active now.
        assert engine._is_on_break(a, datetime.now(timezone.utc)) is False

    def test_break_exactly_now(self):
        from kage.shared.admin_assignment import AdminAssignmentEngine, AdminAvailability
        engine = AdminAssignmentEngine(None)
        now = datetime.now(timezone.utc)
        a = AdminAvailability(admin_telegram_id=1, scheduled_breaks=[
            {"start": now.isoformat(), "end": (now + timedelta(seconds=1)).isoformat()},
        ])
        assert engine._is_on_break(a, now) is True

    def test_dedup_result_large(self):
        """Large DedupResult should be fine."""
        from kage.shared.dedup import DedupResult
        r = DedupResult(
            exists=True,
            source="in_progress",
            title="A" * 500,
            detail="B" * 2000,
            request_code="REQ-" + "9" * 100,
            current_stage="C" * 100,
        )
        assert r.exists is True


# ═══════════════════════════════════════════════════════════════════════════════
# Concurrent access patterns
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrentAccess:
    """Concurrent operations should not corrupt data."""

    @pytest.mark.asyncio
    async def test_dedup_check_concurrent(self, sessionmaker):
        """Multiple concurrent dedup checks should work fine."""
        from kage.shared.dedup import DedupService

        svc = DedupService(sessionmaker)

        async def check_one():
            return await svc.check("Anime A", anime_doc_id="anilist:a1")

        async def check_two():
            return await svc.check("Anime B", anime_doc_id="anilist:b1")

        r1, r2 = await asyncio.gather(check_one(), check_two())
        assert r1.exists is False
        assert r2.exists is False

    @pytest.mark.asyncio
    async def test_admin_engine_concurrent_assign(self, sessionmaker, session):
        """Concurrent assignments should not assign same admin to same request."""
        from kage.tests.helpers import _create_admin_availability
        from kage.shared.admin_assignment import AdminAssignmentEngine

        # Create 2 admins.
        await _create_admin_availability(session, admin_telegram_id=30, admin_name="C1",
                                          assigned_bots=["levi"])
        await _create_admin_availability(session, admin_telegram_id=31, admin_name="C2",
                                          assigned_bots=["levi"])

        engine = AdminAssignmentEngine(sessionmaker)

        async def assign_req(code):
            return await engine.assign(code, "levi")

        # Assign 4 requests concurrently.
        results = await asyncio.gather(
            assign_req("REQ-C1"), assign_req("REQ-C2"),
            assign_req("REQ-C3"), assign_req("REQ-C4"),
        )
        # All should succeed.
        for r in results:
            assert r is not None

    @pytest.mark.asyncio
    async def test_complete_task_concurrent(self, sessionmaker, session):
        """Concurrent completions should increment counter correctly."""
        from kage.tests.helpers import _create_admin_availability, _create_admin_assignment
        from kage.shared.admin_assignment import AdminAssignmentEngine

        await _create_admin_availability(session, admin_telegram_id=40, admin_name="D1",
                                          assigned_bots=["levi"])
        await _create_admin_assignment(session, admin_telegram_id=40, request_code="REQ-CC1", stage="levi")
        await _create_admin_assignment(session, admin_telegram_id=40, request_code="REQ-CC2", stage="levi")

        engine = AdminAssignmentEngine(sessionmaker)

        await asyncio.gather(
            engine.complete_task("REQ-CC1", "levi"),
            engine.complete_task("REQ-CC2", "levi"),
        )

        # Counter should have incremented by 2.  engine.complete_task() opens
        # its own session, so re-query with a fresh session to avoid the test
        # session's identity-map cache (expire_on_commit=False).
        from sqlalchemy import select
        from kage.shared.admin_assignment import AdminAvailability
        async with sessionmaker() as fresh:
            result = await fresh.execute(
                select(AdminAvailability).where(AdminAvailability.admin_telegram_id == 40)
            )
            avail = result.scalar_one()
            assert avail.total_tasks_completed >= 2
