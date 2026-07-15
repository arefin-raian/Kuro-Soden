"""Kage test infrastructure — SQLite in-memory by default; PostgreSQL when
``KAGE_TEST_DATABASE_URL`` is set in the environment.

Session-scoped engine for speed. Session fixture rolls back for isolation.
Set ``KAGE_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host/db`` to run
the full suite against PostgreSQL (all 291 tests pass).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ``pytest_configure`` is the earliest hook; set the event-loop policy here
# so pytest-asyncio inherits it when creating the per-session loop.  Both
# asyncpg and psycopg require SelectorEventLoop on Windows (ProactorEventLoop
# is incompatible with SQLAlchemy's greenlet-based async execution).
def pytest_configure(config):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_DATABASE_URL = os.environ.get("KAGE_TEST_DATABASE_URL", "")

if not _DATABASE_URL:
    # SQLite: register JSONB→JSON compilation so the ORM models work.
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_as_json(type_, compiler, **kw):
        return "JSON"


@pytest_asyncio.fixture(scope="session")
async def engine():
    if _DATABASE_URL:
        # Large pool so concurrent tests + service-owned sessions don't exhaust it.
        eng = create_async_engine(
            _DATABASE_URL, echo=False, pool_size=25, max_overflow=50,
        )
    else:
        eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    import nekofetch.infrastructure.database.postgres.models  # noqa: F401
    import kage.shared.models  # noqa: F401
    from nekofetch.infrastructure.database.postgres.base import Base
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(sessionmaker):
    """Per-test session; helpers ``commit()`` so cross-session services
    (DedupService, AdminAssignmentEngine) can see fixture data.
    One-shot CASCADE TRUNCATE for PostgreSQL after the test to guarantee
    isolation — preceded by a rollback to release any held row locks."""
    async with sessionmaker() as s:
        yield s
        await s.rollback()
    if not _DATABASE_URL:
        return
    from nekofetch.infrastructure.database.postgres.base import Base
    tables = ', '.join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with sessionmaker() as cleanup:
        await cleanup.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
        await cleanup.commit()


from kage.tests.helpers import (  # noqa: E402
    _create_user, _create_request, _create_channel_post,
    _create_distribution_bot, _create_admin_availability, _create_admin_assignment,
)


@pytest_asyncio.fixture
async def user(session):
    return await _create_user(session)

@pytest_asyncio.fixture
async def admin_user(session):
    return await _create_user(session, telegram_id=99999, role="admin",
                              username="admin", first_name="Admin")

@pytest_asyncio.fixture
async def staff_user(session):
    return await _create_user(session, telegram_id=88888, role="staff",
                              username="staff_user", first_name="Staff")

@pytest_asyncio.fixture
async def pending_request(session, user):
    return await _create_request(session, user_id=user.id, status="pending")

@pytest_asyncio.fixture
async def queued_request(session, user):
    return await _create_request(session, code="REQ-0002", user_id=user.id, status="queued")

@pytest_asyncio.fixture
async def published_request(session, user):
    return await _create_request(session, code="REQ-0003", user_id=user.id,
                                 status="published", anime_title="Published Anime")

@pytest_asyncio.fixture
async def channel_post(session):
    return await _create_channel_post(session)

@pytest_asyncio.fixture
async def distribution_bot(session):
    return await _create_distribution_bot(session)

@pytest_asyncio.fixture
async def admin_availability(session):
    return await _create_admin_availability(session)

@pytest_asyncio.fixture
async def admin_assignment(session, admin_availability):
    return await _create_admin_assignment(
        session, admin_telegram_id=admin_availability.admin_telegram_id)
