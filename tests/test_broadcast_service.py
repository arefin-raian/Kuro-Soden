"""Coverage for :class:`BroadcastService` — post one message to every channel.

Runs against the SQLite fixture engine + a fake admin client, so no Telegram
calls happen. Verifies:

  • fan-out hits only enabled distribution *channels* (never the main channel,
    never bots), and one delivered copy is recorded per channel;
  • a timed broadcast stamps every row with a future ``delete_at``; a permanent
    one leaves it ``None``;
  • ``sweep_expired`` deletes only past-due, not-yet-deleted rows, marks them
    done, and is idempotent (a second sweep is a no-op);
  • a per-channel send failure is counted, doesn't abort the run, and yields no
    orphan row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from nekofetch.infrastructure.database.postgres.models import (
    ChannelBroadcast,
    DistributionBot,
)
from nekofetch.services.broadcast_service import BroadcastService

pytestmark = pytest.mark.asyncio


class _FakeClient:
    """Records copies/sends/deletes; hands out increasing message ids."""

    def __init__(self, *, fail_on: set[int] | None = None):
        self.copies: list[tuple[int, int]] = []      # (to_chat, from_msg)
        self.sends: list[tuple[int, str]] = []       # (chat, text)
        self.deleted: list[tuple[int, int]] = []     # (chat, message_id)
        self._next_id = 5000
        self._fail_on = fail_on or set()

    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        if chat_id in self._fail_on:
            raise RuntimeError("CHAT_WRITE_FORBIDDEN")
        self._next_id += 1
        self.copies.append((chat_id, message_id))
        return SimpleNamespace(id=self._next_id)

    async def send_message(self, chat_id, text, **kw):
        self._next_id += 1
        self.sends.append((chat_id, text))
        return SimpleNamespace(id=self._next_id)

    async def delete_messages(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


def _container(sessionmaker, client):
    return SimpleNamespace(
        pg_sessionmaker=sessionmaker,
        admin_client=client,
        redis=None,
    )


async def _make_channels(session):
    """Two enabled channels, one disabled channel, one bot — only the two
    enabled channels should ever receive a broadcast."""
    rows = [
        DistributionBot(name="A", username=None, anime_doc_id="anilist:1",
                        encrypted_token="x", enabled=True, is_channel=True, chat_id=-100_1),
        DistributionBot(name="B", username=None, anime_doc_id="anilist:2",
                        encrypted_token="x", enabled=True, is_channel=True, chat_id=-100_2),
        DistributionBot(name="Disabled", username=None, anime_doc_id="anilist:3",
                        encrypted_token="x", enabled=False, is_channel=True, chat_id=-100_3),
        DistributionBot(name="Bot", username="a_bot", anime_doc_id="anilist:4",
                        encrypted_token="x", enabled=True, is_channel=False, chat_id=-100_4),
    ]
    session.add_all(rows)
    await session.commit()
    return rows


async def _all_rows(sessionmaker):
    async with sessionmaker() as s:
        return (await s.execute(select(ChannelBroadcast))).scalars().all()


# ── fan-out targets ───────────────────────────────────────────────────────────

async def test_broadcast_hits_only_enabled_channels(sessionmaker, session):
    await _make_channels(session)
    client = _FakeClient()
    svc = BroadcastService(_container(sessionmaker, client))

    result = await svc.broadcast_copy(from_chat_id=777, message_id=42)

    # Only the two enabled channels (-100_1, -100_2); disabled + bot skipped.
    assert result.targets == 2
    assert result.sent == 2
    assert result.failed == 0
    assert sorted(c for c, _ in client.copies) == [-100_2, -100_1]

    rows = await _all_rows(sessionmaker)
    assert len(rows) == 2
    assert {r.batch_id for r in rows} == {result.batch_id}
    assert all(r.delete_at is None and r.deleted is False for r in rows)


async def test_broadcast_text_fans_out(sessionmaker, session):
    await _make_channels(session)
    client = _FakeClient()
    svc = BroadcastService(_container(sessionmaker, client))

    result = await svc.broadcast_text("hello channels")
    assert result.sent == 2
    assert sorted(t for _, t in client.sends) == ["hello channels", "hello channels"]


# ── timed vs permanent ──────────────────────────────────────────────────────

async def test_timed_broadcast_stamps_delete_at(sessionmaker, session):
    await _make_channels(session)
    client = _FakeClient()
    svc = BroadcastService(_container(sessionmaker, client))

    before = datetime.now(timezone.utc)
    result = await svc.broadcast_copy(
        from_chat_id=777, message_id=42, delete_after_minutes=60,
    )
    assert result.delete_at is not None
    # ~60 minutes out (allow slack for test runtime).
    delta = result.delete_at - before
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)

    rows = await _all_rows(sessionmaker)
    assert all(r.delete_at is not None for r in rows)


# ── sweep ────────────────────────────────────────────────────────────────────

async def test_sweep_deletes_only_past_due(sessionmaker, session):
    await _make_channels(session)
    client = _FakeClient()
    svc = BroadcastService(_container(sessionmaker, client))
    now = datetime.now(timezone.utc)

    async with sessionmaker() as s:
        s.add_all([
            # past-due — should be swept
            ChannelBroadcast(batch_id="b", chat_id=-100_1, message_id=11,
                             delete_at=now - timedelta(minutes=5), deleted=False),
            # future — must be left alone
            ChannelBroadcast(batch_id="b", chat_id=-100_2, message_id=12,
                             delete_at=now + timedelta(hours=1), deleted=False),
            # permanent — must be left alone
            ChannelBroadcast(batch_id="b", chat_id=-100_1, message_id=13,
                             delete_at=None, deleted=False),
        ])
        await s.commit()

    swept = await svc.sweep_expired()
    assert swept == 1
    assert client.deleted == [(-100_1, 11)]

    rows = {r.message_id: r for r in await _all_rows(sessionmaker)}
    assert rows[11].deleted is True
    assert rows[12].deleted is False
    assert rows[13].deleted is False

    # Idempotent: nothing left past-due.
    assert await svc.sweep_expired() == 0


async def test_sweep_marks_done_even_if_delete_raises(sessionmaker, session):
    client = _FakeClient()

    async def _boom(chat_id, message_id):
        raise RuntimeError("MESSAGE_ID_INVALID")

    client.delete_messages = _boom  # type: ignore[assignment]
    svc = BroadcastService(_container(sessionmaker, client))
    now = datetime.now(timezone.utc)
    async with sessionmaker() as s:
        s.add(ChannelBroadcast(batch_id="b", chat_id=-100_1, message_id=11,
                               delete_at=now - timedelta(minutes=5), deleted=False))
        await s.commit()

    # A stale/gone message still resolves the row so the sweep can't loop on it.
    assert await svc.sweep_expired() == 1
    rows = await _all_rows(sessionmaker)
    assert rows[0].deleted is True


# ── partial failure ──────────────────────────────────────────────────────────

async def test_send_failure_counts_and_leaves_no_orphan_row(sessionmaker, session):
    await _make_channels(session)
    client = _FakeClient(fail_on={-100_1})   # first channel refuses
    svc = BroadcastService(_container(sessionmaker, client))

    result = await svc.broadcast_copy(from_chat_id=777, message_id=42)
    assert result.targets == 2
    assert result.sent == 1
    assert result.failed == 1
    assert len(result.errors) == 1

    rows = await _all_rows(sessionmaker)
    # Only the channel that succeeded gets a row.
    assert len(rows) == 1
    assert rows[0].chat_id == -100_2


async def test_no_channels_is_safe(sessionmaker, session):
    client = _FakeClient()
    svc = BroadcastService(_container(sessionmaker, client))
    result = await svc.broadcast_copy(from_chat_id=1, message_id=1)
    assert result.targets == 0 and result.sent == 0
    assert await _all_rows(sessionmaker) == []


async def test_no_client_is_safe(sessionmaker, session):
    await _make_channels(session)
    svc = BroadcastService(_container(sessionmaker, None))
    result = await svc.broadcast_copy(from_chat_id=1, message_id=1, client=None)
    assert result.sent == 0 and result.targets == 0
