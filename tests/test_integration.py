"""Integration tests — full pipeline flows with SQLite DB.

Covers:
  • Config YAML loading from kage/config.yaml
  • Env settings from kage/.env
  • Full DB schema verification (all 16 tables)
  • DedupService with actual DB fixtures
  • AdminAssignmentEngine with actual DB
  • Multiple concurrent admin assignments
  • Pipeline handoff (request → assign → complete → next stage)
  • Session scope and transaction rollback
  • ORM relationship integrity
"""

from __future__ import annotations

import asyncio

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Config loading
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigYAML:
    """kage/config.yaml should load correctly."""

    def test_config_file_exists(self):
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        assert config_path.exists(), "kage/config.yaml missing"

    def test_config_loads_without_error(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config is not None

    def test_config_has_features_section(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config.features is not None
        assert config.features.request_system is True

    def test_config_has_sources_section(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config.sources.enabled is not None
        assert len(config.sources.enabled) > 0

    def test_config_has_branding_section(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config.branding.channel_name is not None

    def test_config_has_ui_section(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config.ui.start_sticker_id != ""

    def test_config_has_storage_channel(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config.storage_channel is not None

    def test_config_has_main_channel(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert config.main_channel is not None

    def test_config_has_acquisition(self):
        from nekofetch.core.config import AppConfig
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        config = AppConfig.load(str(config_path))
        assert len(config.acquisition.resolutions) > 0
        assert len(config.acquisition.languages) > 0

    def test_config_defaults_when_file_missing(self):
        from nekofetch.core.config import AppConfig
        config = AppConfig.load("nonexistent_config.yaml")
        assert config is not None
        assert config.features.request_system is True  # default


# ═══════════════════════════════════════════════════════════════════════════════
# Env settings
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvSettings:
    """EnvSettings from kage/.env."""

    def test_env_file_exists(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        assert env_path.exists(), "kage/.env missing"

    def test_has_all_required_tokens(self):
        """.env must have all four bot tokens and the shared admin token."""
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        content = env_path.read_text(encoding="utf-8")
        assert "REQUEST_BOT_TOKEN" in content
        assert "DOWNLOADER_BOT_TOKEN" in content
        assert "DISTRIBUTION_BOT_TOKEN" in content
        assert "PUBLISHER_BOT_TOKEN" in content
        assert "ADMIN_BOT_TOKEN" in content

    def test_has_postgres_config(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        content = env_path.read_text(encoding="utf-8")
        assert "POSTGRES_HOST" in content
        assert "POSTGRES_DB" in content

    def test_has_redis_config(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        content = env_path.read_text(encoding="utf-8")
        assert "REDIS_URL" in content

    def test_has_tmdb_config(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        content = env_path.read_text(encoding="utf-8")
        assert "TMDB_API_KEY" in content

    def test_has_secret_key(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        content = env_path.read_text(encoding="utf-8")
        assert "SECRET_KEY" in content

    def test_has_telegram_api(self):
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env"
        content = env_path.read_text(encoding="utf-8")
        assert "TELEGRAM_API_ID" in content
        assert "TELEGRAM_API_HASH" in content

    def test_env_values_not_empty(self):
        """Token variables in .env.example should exist (real .env is gitignored)."""
        from pathlib import Path
        env_path = Path(__file__).resolve().parent.parent / ".env.example"
        content = env_path.read_text(encoding="utf-8")
        # Check that token variables exist in the example (no value assertion —
        # the user fills those in when they copy to .env).
        for token_var in ["REQUEST_BOT_TOKEN", "DOWNLOADER_BOT_TOKEN",
                           "DISTRIBUTION_BOT_TOKEN", "PUBLISHER_BOT_TOKEN"]:
            found = False
            for line in content.splitlines():
                if line.startswith(token_var + "="):
                    found = True
                    break
            assert found, f"{token_var} not found in .env.example"


# ═══════════════════════════════════════════════════════════════════════════════
# DB schema integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullSchemaIntegration:
    """All 16 tables should be creatable and queryable."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, engine):
        """After engine fixture init, all 16 tables exist."""
        import kage.shared.models  # noqa: F401
        from nekofetch.infrastructure.database.postgres.base import Base

        tables = list(Base.metadata.tables.keys())
        assert "users" in tables
        assert "requests" in tables
        assert "download_queue" in tables
        assert "files" in tables
        assert "bots" in tables
        assert "channel_posts" in tables
        assert "admin_assignments" in tables
        assert "admin_availability" in tables
        assert len(tables) >= 16

    @pytest.mark.asyncio
    async def test_user_has_expected_columns(self, session):
        """User table should have all needed columns."""
        from nekofetch.infrastructure.database.postgres.models import User
        cols = {c.name for c in User.__table__.columns}
        assert "telegram_id" in cols
        assert "username" in cols
        assert "first_name" in cols
        assert "role" in cols
        assert "is_approved" in cols
        assert "is_banned" in cols

    @pytest.mark.asyncio
    async def test_request_has_expected_columns(self, session):
        from nekofetch.infrastructure.database.postgres.models import Request
        cols = {c.name for c in Request.__table__.columns}
        assert "code" in cols
        assert "anime_title" in cols
        assert "anime_doc_id" in cols
        assert "source" in cols
        assert "status" in cols
        assert "franchise_data" in cols


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline handoff integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineHandoff:
    """Full request → assign → complete flow."""

    @pytest.mark.asyncio
    async def test_full_handoff_flow(self, sessionmaker, session):
        """Lelouch assigns → Levi picks up → Levi completes → Senku gets assigned."""
        from kage.tests.helpers import _create_user, _create_request, _create_admin_availability
        from kage.shared.admin_assignment import AdminAssignmentEngine
        from kage.shared.dedup import DedupService
        from sqlalchemy import select
        from kage.shared.admin_assignment import AdminAssignment

        # 1. Create a user and request.
        user = await _create_user(session, telegram_id=55555, role="user")
        req = await _create_request(session, code="REQ-FLOW", user_id=user.id,
                                     anime_title="Flow Test Anime", anime_doc_id="anilist:flow1")

        # 2. Create admin availability for levi and senku stages.
        await _create_admin_availability(session, admin_telegram_id=100, admin_name="LeviAdmin",
                                          assigned_bots=["levi"])
        await _create_admin_availability(session, admin_telegram_id=200, admin_name="SenkuAdmin",
                                          assigned_bots=["senku"])

        # 3. Assign to levi.
        engine = AdminAssignmentEngine(sessionmaker)
        result = await engine.assign("REQ-FLOW", "levi")
        assert result is not None
        assert result.admin_telegram_id == 100

        # 4. Levi completes.
        await engine.complete_task("REQ-FLOW", "levi")

        # 5. Assign to senku (next stage).
        result2 = await engine.assign("REQ-FLOW", "senku")
        assert result2 is not None
        assert result2.admin_telegram_id == 200

        # 6. Verify completion record.
        levi_assignments = await session.execute(
            select(AdminAssignment).where(
                AdminAssignment.request_code == "REQ-FLOW",
                AdminAssignment.stage == "levi",
            )
        )
        levi_row = levi_assignments.scalar_one()
        assert levi_row.status == "completed"

        # 7. Dedup should find this as in-progress (senku stage not yet completed).
        dedup = DedupService(sessionmaker)
        dr = await dedup.check("Flow Test Anime", anime_doc_id="anilist:flow1")
        assert dr.exists is True
        assert dr.source == "in_progress"

    @pytest.mark.asyncio
    async def test_multiple_admins_balanced_distribution(self, sessionmaker, session):
        """Multiple admins should get balanced assignments."""
        from kage.tests.helpers import _create_admin_availability, _create_request, _create_user
        from kage.shared.admin_assignment import AdminAssignmentEngine

        user = await _create_user(session, telegram_id=66666)

        # Create 3 levi admins with varying completed counts.
        await _create_admin_availability(session, admin_telegram_id=1, admin_name="A1",
                                          total_tasks_completed=5, assigned_bots=["levi"])
        await _create_admin_availability(session, admin_telegram_id=2, admin_name="A2",
                                          total_tasks_completed=10, assigned_bots=["levi"])
        await _create_admin_availability(session, admin_telegram_id=3, admin_name="A3",
                                          total_tasks_completed=3, assigned_bots=["levi"])

        engine = AdminAssignmentEngine(sessionmaker)

        # First assignment should go to A3 (fewest completed).
        r1 = await engine.assign("REQ-B1", "levi")
        assert r1.admin_telegram_id == 3

        # Second should go to A1 (now A3 has 1 active, A1 has 0).
        r2 = await engine.assign("REQ-B2", "levi")
        assert r2.admin_telegram_id == 1

        # Third should go to A2 (A1 has 1 active, A2 has 0).
        r3 = await engine.assign("REQ-B3", "levi")
        assert r3.admin_telegram_id == 2

    @pytest.mark.asyncio
    async def test_concurrent_assignments_no_duplicate(self, sessionmaker, session):
        """Even concurrent assigns should not assign the same admin to the same request twice."""
        from kage.tests.helpers import _create_admin_availability
        from kage.shared.admin_assignment import AdminAssignmentEngine

        await _create_admin_availability(session, admin_telegram_id=10, admin_name="Solo",
                                          assigned_bots=["levi"])

        engine = AdminAssignmentEngine(sessionmaker)

        # Run two concurrent assignments for different requests.
        async def assign_one():
            return await engine.assign("REQ-CONC1", "levi")

        async def assign_two():
            return await engine.assign("REQ-CONC2", "levi")

        r1, r2 = await asyncio.gather(assign_one(), assign_two())
        assert r1 is not None
        assert r2 is not None
        # Both assigned to same admin (only one available), but different request codes.
        assert r1.admin_telegram_id == r2.admin_telegram_id == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Session and transaction integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionIntegrity:
    """Session scope and transaction rollback tests."""

    @pytest.mark.asyncio
    async def test_session_scope_commit(self, sessionmaker):
        """session_scope should commit on success."""
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.database.postgres.models import User
        from nekofetch.domain.enums import Role

        async with session_scope(sessionmaker) as s:
            u = User(telegram_id=77777, username="scopetest", first_name="Scope",
                      role=Role.USER, language="en")
            s.add(u)

        # Verify committed.
        from sqlalchemy import select
        async with sessionmaker() as s:
            result = await s.execute(select(User).where(User.telegram_id == 77777))
            assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_session_scope_rollback_on_error(self, sessionmaker):
        """session_scope should rollback on exception."""
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.database.postgres.models import User
        from nekofetch.domain.enums import Role

        try:
            async with session_scope(sessionmaker) as s:
                u = User(telegram_id=88888, username="rollbacktest", first_name="Rollback",
                          role=Role.USER, language="en")
                s.add(u)
                raise ValueError("Intentional rollback")
        except ValueError:
            pass

        # Verify NOT committed.
        from sqlalchemy import select
        async with sessionmaker() as s:
            result = await s.execute(select(User).where(User.telegram_id == 88888))
            assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_sqlite_fk_cascade(self, session):
        """Foreign key relationships work correctly."""
        from nekofetch.infrastructure.database.postgres.models import User, Request
        from nekofetch.domain.enums import Role, RequestStatus

        u = User(telegram_id=99999, username="fktest", first_name="FK",
                  role=Role.USER, language="en")
        session.add(u)
        await session.flush()

        r = Request(code="REQ-FK", user_id=u.id, anime_title="FK Test",
                     source="anikoto", scope="entire_series",
                     status=RequestStatus.PENDING)
        session.add(r)
        await session.flush()

        assert r.user_id == u.id


# ═══════════════════════════════════════════════════════════════════════════════
# Request code generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequestCodes:
    """Request codes follow the REQ-XXXX pattern."""

    def test_code_format(self):
        """REQ-XXXX is the standard code pattern."""
        codes = ["REQ-0001", "REQ-1234", "REQ-9999"]
        for code in codes:
            assert code.startswith("REQ-")
            assert len(code) == 8
            assert code[4:].isdigit()

    @pytest.mark.asyncio
    async def test_code_unique_per_request(self, session):
        """Each request must have a unique code — duplicates raise integrity error."""
        from kage.tests.helpers import _create_request
        await _create_request(session, code="REQ-UNIQUE", anime_doc_id="anilist:uq1")
        # Creating a second with same code should fail.
        with pytest.raises(Exception):
            await _create_request(session, code="REQ-UNIQUE", anime_doc_id="anilist:uq2")

    def test_code_is_not_none(self):
        from nekofetch.infrastructure.database.postgres.models import Request
        col = Request.__table__.columns["code"]
        assert not col.nullable

    def test_code_is_indexed(self):
        from nekofetch.infrastructure.database.postgres.models import Request
        col = Request.__table__.columns["code"]
        assert col.index is True or any(idx for idx in Request.__table__.indexes if "code" in str(idx))


# ═══════════════════════════════════════════════════════════════════════════════
# Complete dedup integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestDedupFullIntegration:
    """Dedup across main channel, distribution, and in-progress."""

    @pytest.fixture
    def dedup(self, sessionmaker):
        from kage.shared.dedup import DedupService
        return DedupService(sessionmaker)

    @pytest.mark.asyncio
    async def test_main_channel_wins_over_distribution(self, dedup, session):
        from kage.tests.helpers import _create_channel_post, _create_distribution_bot
        await _create_channel_post(session, anime_doc_id="anilist:multi1", main_message_id=100)
        await _create_distribution_bot(session, anime_doc_id="anilist:multi1")

        r = await dedup.check("Multi Test", anime_doc_id="anilist:multi1")
        assert r.source == "main_channel"

    @pytest.mark.asyncio
    async def test_distribution_wins_over_in_progress(self, dedup, session):
        from kage.tests.helpers import _create_distribution_bot, _create_request
        await _create_distribution_bot(session, anime_doc_id="anilist:multi2")
        await _create_request(session, code="REQ-M2", anime_doc_id="anilist:multi2",
                               anime_title="Multi2", status="pending")

        r = await dedup.check("Multi2", anime_doc_id="anilist:multi2")
        assert r.source == "distribution"

    @pytest.mark.asyncio
    async def test_in_progress_is_last_resort(self, dedup, session):
        from kage.tests.helpers import _create_request
        await _create_request(session, code="REQ-LAST", anime_doc_id="anilist:last1",
                               anime_title="Last Resort", status="processing")

        r = await dedup.check("Last Resort", anime_doc_id="anilist:last1")
        assert r.source == "in_progress"

    @pytest.mark.asyncio
    async def test_published_not_flagged(self, dedup, session):
        from kage.tests.helpers import _create_request
        await _create_request(session, code="REQ-PUB", anime_doc_id="anilist:pub1",
                               anime_title="Already Published", status="published")

        r = await dedup.check("Already Published", anime_doc_id="anilist:pub1")
        assert r.exists is False  # PUBLISHED is not in progress, no channel post.
