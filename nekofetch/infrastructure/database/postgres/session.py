"""Postgres session utilities and schema creation helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nekofetch.infrastructure.database.postgres.base import Base


@asynccontextmanager
async def session_scope(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transactional session scope: commit on success, rollback on error."""
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all(engine) -> None:
    """Create tables + required sequences for first-run/dev.

    Production also runs Alembic, but the container boots with ``python main.py``
    (no ``alembic upgrade head``), so anything NOT expressed in ``Base.metadata``
    — like the raw ``request_code_seq`` sequence that backs collision-free request
    codes — must be created here too, or every request submit crashes with
    ``relation "request_code_seq" does not exist``. Idempotent on every backend.
    """
    from sqlalchemy import text

    # Import models so they register on Base.metadata.
    from nekofetch.infrastructure.database.postgres import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ``request_code_seq`` is a bare Postgres sequence (see request_repo
        # .next_sequence + migration 0009), not an ORM table, so create_all above
        # never emits it. SQLite has no CREATE SEQUENCE and the test suite stubs
        # next_sequence differently, so this is Postgres-only.
        if conn.dialect.name == "postgresql":
            # Seed ONLY on first creation. Running setval every boot would reset the
            # counter to MAX(code)+1 each time — so deleting the newest request then
            # rebooting would reissue its code (the exact collision the sequence
            # exists to prevent). ``to_regclass`` returns NULL when the sequence is
            # absent, which is our "freshly creating it now" signal.
            already = (
                await conn.execute(text("SELECT to_regclass('request_code_seq')"))
            ).scalar()
            await conn.execute(
                text("CREATE SEQUENCE IF NOT EXISTS request_code_seq MINVALUE 1")
            )
            if already is None:
                # Start just past the highest existing REQ-<n> so a fresh sequence on
                # an already-populated DB never reissues a live code. is_called=false
                # → the very next nextval() returns exactly the computed floor.
                start = (
                    await conn.execute(
                        text(
                            "SELECT COALESCE(MAX(CAST(substring(code from 'REQ-([0-9]+)') "
                            "AS INTEGER)), 1048) + 1 FROM requests"
                        )
                    )
                ).scalar()
                await conn.execute(
                    text("SELECT setval('request_code_seq', :n, false)").bindparams(
                        n=int(start or 1049)
                    )
                )
