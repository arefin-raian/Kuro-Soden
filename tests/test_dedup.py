"""Tests for kage/shared/dedup.py — Duplicate detection service.

Covers:
  • DedupResult dataclass defaults, field assignments, edge cases
  • DedupService._build_in_progress_result() with all statuses
  • Full dedup pipeline with SQLite in-memory DB
  • Edge cases: empty titles, None doc_ids, unicode
"""

from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# DedupResult dataclass — pure data, no DB needed
# ═══════════════════════════════════════════════════════════════════════════════

class TestDedupResultDefaults:
    """Default values should be sensible."""

    def test_default_exists_is_false(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.exists is False

    def test_default_source_is_empty(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.source == ""

    def test_default_title_is_empty(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.title == ""

    def test_default_detail_is_empty(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.detail == ""

    def test_default_bot_username_is_none(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.bot_username is None

    def test_default_main_channel_link_is_none(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.main_channel_link is None

    def test_default_request_code_is_none(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.request_code is None

    def test_default_current_stage_is_none(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult()
        assert r.current_stage is None


class TestDedupResultFields:
    """All fields should be assignable."""

    def test_main_channel_result(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(
            exists=True,
            source="main_channel",
            title="Test Anime",
            detail='「Test Anime」is already available!',
            main_channel_link="https://t.me/c/123/55",
        )
        assert r.exists is True
        assert r.source == "main_channel"
        assert r.title == "Test Anime"
        assert r.main_channel_link == "https://t.me/c/123/55"

    def test_distribution_result(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(
            exists=True,
            source="distribution",
            title="Test Anime",
            detail="via @testbot_axw",
            bot_username="testbot_axw",
        )
        assert r.bot_username == "testbot_axw"
        assert r.source == "distribution"

    def test_in_progress_result(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(
            exists=True,
            source="in_progress",
            title="Test Anime",
            request_code="REQ-0001",
            current_stage="downloading",
        )
        assert r.request_code == "REQ-0001"
        assert r.current_stage == "downloading"

    def test_no_match_result(self):
        from kage.shared.dedup import DedupResult
        r = DedupResult(exists=False)
        assert r.exists is False
        assert r.source == ""
        assert r.bot_username is None
        assert r.request_code is None

    def test_unicode_title(self):
        """Japanese/unicode titles should work fine."""
        from kage.shared.dedup import DedupResult
        r = DedupResult(
            exists=True,
            source="main_channel",
            title="進撃の巨人",
            detail="「進撃の巨人」is available!",
        )
        assert "進撃の巨人" in r.detail

    def test_emoji_title(self):
        """Titles with emoji should work."""
        from kage.shared.dedup import DedupResult
        r = DedupResult(title="🎬 Movie Test ✨")
        assert r.title == "🎬 Movie Test ✨"

    def test_very_long_title(self):
        """Extremely long titles shouldn't crash."""
        from kage.shared.dedup import DedupResult
        long_title = "A" * 500
        r = DedupResult(title=long_title)
        assert len(r.title) == 500


# ═══════════════════════════════════════════════════════════════════════════════
# DedupService._build_in_progress_result — static method, no DB needed
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildInProgressResult:
    """_build_in_progress_result produces the right result for each status."""

    @pytest.fixture
    def svc(self, sessionmaker):
        from kage.shared.dedup import DedupService
        return DedupService(sessionmaker)

    async def _make_req(self, session, **kw):
        """Create a Request row for _build_in_progress_result testing."""
        from kage.tests.helpers import _create_request
        return await _create_request(session, **kw)

    @pytest.mark.asyncio
    async def test_pending_status(self, svc, session):
        req = await self._make_req(session, status="pending", code="REQ-0001", anime_title="My Anime")
        r = svc._build_in_progress_result(req)
        assert r.exists is True
        assert r.source == "in_progress"
        assert r.request_code == "REQ-0001"
        assert "awaiting source assignment" in r.detail
        assert "My Anime" in r.detail

    @pytest.mark.asyncio
    async def test_approved_status(self, svc, session):
        req = await self._make_req(session, status="approved", code="REQ-0002")
        r = svc._build_in_progress_result(req)
        assert "approved" in r.current_stage

    @pytest.mark.asyncio
    async def test_queued_status(self, svc, session):
        req = await self._make_req(session, status="queued", code="REQ-0003")
        r = svc._build_in_progress_result(req)
        assert "download queue" in r.current_stage

    @pytest.mark.asyncio
    async def test_downloading_status(self, svc, session):
        req = await self._make_req(session, status="downloading", code="REQ-0004")
        r = svc._build_in_progress_result(req)
        assert "currently downloading" in r.current_stage

    @pytest.mark.asyncio
    async def test_processing_status(self, svc, session):
        req = await self._make_req(session, status="processing", code="REQ-0005")
        r = svc._build_in_progress_result(req)
        assert "being processed" in r.current_stage

    @pytest.mark.asyncio
    async def test_ready_status(self, svc, session):
        req = await self._make_req(session, status="ready", code="REQ-0006")
        r = svc._build_in_progress_result(req)
        assert "awaiting publishing" in r.current_stage

    @pytest.mark.asyncio
    async def test_unknown_status_falls_back_to_raw(self, svc, session):
        """An unknown status string should be displayed as-is."""
        req = await self._make_req(session, status="pending", code="REQ-X")
        # Force status to a raw string not in stage_labels.
        req.status = "some_weird_status_value"
        r = svc._build_in_progress_result(req)
        assert "some_weird_status_value" in r.current_stage

    @pytest.mark.asyncio
    async def test_detail_contains_code(self, svc, session):
        req = await self._make_req(session, code="REQ-9999", status="pending")
        r = svc._build_in_progress_result(req)
        assert "REQ-9999" in r.detail

    @pytest.mark.asyncio
    async def test_result_title_matches_request(self, svc, session):
        req = await self._make_req(session, anime_title="My Hero Academia", status="downloading")
        r = svc._build_in_progress_result(req)
        assert r.title == "My Hero Academia"


# ═══════════════════════════════════════════════════════════════════════════════
# DedupService — full pipeline with DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestDedupServiceInit:
    """Initialization tests."""

    def test_creates_with_sessionmaker(self, sessionmaker):
        from kage.shared.dedup import DedupService
        svc = DedupService(sessionmaker)
        assert svc is not None
        assert svc._sm is sessionmaker

    def test_in_progress_statuses_set(self, sessionmaker):
        from kage.shared.dedup import DedupService
        from nekofetch.domain.enums import RequestStatus
        svc = DedupService(sessionmaker)
        assert RequestStatus.PENDING in svc._IN_PROGRESS_STATUSES
        assert RequestStatus.QUEUED in svc._IN_PROGRESS_STATUSES
        assert RequestStatus.DOWNLOADING in svc._IN_PROGRESS_STATUSES
        assert RequestStatus.PROCESSING in svc._IN_PROGRESS_STATUSES

    def test_published_not_in_progress(self, sessionmaker):
        from kage.shared.dedup import DedupService
        from nekofetch.domain.enums import RequestStatus
        svc = DedupService(sessionmaker)
        assert RequestStatus.PUBLISHED not in svc._IN_PROGRESS_STATUSES
        assert RequestStatus.FAILED not in svc._IN_PROGRESS_STATUSES
        assert RequestStatus.REJECTED not in svc._IN_PROGRESS_STATUSES


class TestDedupServiceCheck:
    """Full check() pipeline tests."""

    @pytest.fixture
    def svc(self, sessionmaker):
        from kage.shared.dedup import DedupService
        return DedupService(sessionmaker)

    # ── Main channel ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_finds_main_channel_post(self, svc, session, channel_post):
        r = await svc.check("Test Anime", anime_doc_id="anilist:12345")
        assert r.exists is True
        assert r.source == "main_channel"

    @pytest.mark.asyncio
    async def test_no_main_channel_when_missing(self, svc, session):
        r = await svc.check("Missing Anime", anime_doc_id="anilist:nonexistent", _session=session)
        assert r.exists is False

    @pytest.mark.asyncio
    async def test_no_main_channel_without_doc_id(self, svc, session, channel_post):
        """Without anilist doc_id, can't check main channel."""
        r = await svc.check("Test Anime", anime_doc_id=None, _session=session)
        assert r.source != "main_channel"  # Can't match without doc_id

    @pytest.mark.asyncio
    async def test_main_channel_without_message_id(self, svc, session):
        """ChannelPost without main_message_id shouldn't match."""
        from kage.tests.helpers import _create_channel_post
        await _create_channel_post(session, anime_doc_id="anilist:99999", main_message_id=None)
        r = await svc.check("Unpublished Anime", anime_doc_id="anilist:99999", _session=session)
        assert r.source != "main_channel"

    # ── Distribution ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_finds_distribution_bot(self, svc, session, distribution_bot):
        r = await svc.check("Test Anime", anime_doc_id="anilist:12345")
        assert r.exists is True
        assert r.source == "distribution"
        assert r.bot_username == "testbot_axw"

    @pytest.mark.asyncio
    async def test_ignores_disabled_bot(self, svc, session):
        from kage.tests.helpers import _create_distribution_bot
        await _create_distribution_bot(session, anime_doc_id="anilist:disabled", enabled=False)
        r = await svc.check("Disabled Anime", anime_doc_id="anilist:disabled", _session=session)
        assert r.source != "distribution"

    @pytest.mark.asyncio
    async def test_distribution_respects_priority(self, svc, session, channel_post):
        """Main channel should take priority over distribution."""
        from kage.tests.helpers import _create_distribution_bot
        await _create_distribution_bot(session, anime_doc_id="anilist:12345")
        r = await svc.check("Test Anime", anime_doc_id="anilist:12345", _session=session)
        # Main channel is checked first and should win.
        assert r.source == "main_channel"

    # ── In-progress ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_finds_in_progress_by_doc_id(self, svc, session, pending_request):
        r = await svc.check("Test Anime", anime_doc_id="anilist:12345", _session=session)
        assert r.source == "in_progress"
        assert r.request_code == "REQ-0001"

    @pytest.mark.asyncio
    async def test_finds_in_progress_by_title_fuzzy(self, svc, session):
        from kage.tests.helpers import _create_request
        await _create_request(session, anime_doc_id="anilist:99999", anime_title="Attack on Titan Final Season", status="downloading")
        r = await svc.check("Attack on Titan", anime_doc_id=None, _session=session)
        assert r.source == "in_progress"

    @pytest.mark.asyncio
    async def test_fuzzy_match_case_insensitive(self, svc, session):
        from kage.tests.helpers import _create_request
        await _create_request(session, anime_doc_id="anilist:case1", anime_title="Demon Slayer", status="processing")
        r = await svc.check("demon slayer", anime_doc_id=None, _session=session)
        assert r.source == "in_progress"

    @pytest.mark.asyncio
    async def test_no_match_for_published_request(self, svc, session, published_request):
        """PUBLISHED requests are NOT in-progress."""
        r = await svc.check("Published Anime", anime_doc_id="anilist:12345", _session=session)
        assert r.source == ""

    @pytest.mark.asyncio
    async def test_no_match_for_failed_request(self, svc, session):
        from kage.tests.helpers import _create_request
        await _create_request(session, code="REQ-FAIL", status="failed", anime_doc_id="anilist:fail1")
        r = await svc.check("Failed Anime", anime_doc_id="anilist:fail1", _session=session)
        assert r.exists is False

    @pytest.mark.asyncio
    async def test_no_match_for_rejected_request(self, svc, session):
        from kage.tests.helpers import _create_request
        await _create_request(session, code="REQ-REJ", status="rejected", anime_doc_id="anilist:rej1")
        r = await svc.check("Rejected Anime", anime_doc_id="anilist:rej1", _session=session)
        assert r.exists is False

    # ── No match scenarios ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_match_completely_new(self, svc, session):
        """Nothing in the DB at all."""
        r = await svc.check("Brand New Anime", anime_doc_id="anilist:new1", _session=session)
        assert r.exists is False
        assert r.source == ""
        assert r.title == ""

    @pytest.mark.asyncio
    async def test_none_doc_id_no_matches(self, svc, session):
        """Without any doc_id, can't match anything."""
        r = await svc.check("Some Anime", anime_doc_id=None, _session=session)
        assert r.exists is False

    @pytest.mark.asyncio
    async def test_empty_title_no_matches(self, svc, session):
        """Empty title should just return no match (no crash)."""
        r = await svc.check("", anime_doc_id="anilist:anything", _session=session)
        assert r.exists is False

    @pytest.mark.asyncio
    async def test_unicode_title_matching(self, svc, session):
        """Japanese titles should work for fuzzy matching."""
        from kage.tests.helpers import _create_request
        await _create_request(
            session, code="REQ-JP", anime_title="進撃の巨人 The Final Season",
            anime_doc_id="anilist:jp1", status="downloading",
        )
        r = await svc.check("進撃の巨人", anime_doc_id=None, _session=session)
        assert r.source == "in_progress"

    @pytest.mark.asyncio
    async def test_special_characters_in_title(self, svc, session):
        """Special regex characters in titles shouldn't break ILIKE."""
        r = await svc.check("Title with % and _ chars", anime_doc_id=None, _session=session)
        assert r.exists is False  # Should not crash
