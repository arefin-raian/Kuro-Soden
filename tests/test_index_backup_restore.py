"""Index-scope backup & restore round-trip (Phase 5, workstream D+).

A banned *index* channel must be rebuildable verbatim on a fresh channel: the
pinned poster and every slot (labelled letter sections + trailing reserved
slots) are captured into a wipe-proof :class:`ChannelContentBackup`, then
reposted in order onto a new channel with every ``IndexSection.message_id``
remapped and the index-channel config (id / username / poster id) repointed so
future t.me links follow.

Runs against the SQLite fixture + a fake admin client with the image mirror
stubbed — no Telegram / catbox / envs.sh calls happen.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from nekofetch.core.config import IndexChannelConfig
from nekofetch.infrastructure.database.postgres.models import (
    ChannelContentBackup,
    IndexSection,
    StoragePack,
)
from nekofetch.services.backup_service import BackupService
from kurosoden.shared.image_backup import BackupImage

pytestmark = pytest.mark.asyncio


class _FakeMsg:
    def __init__(self, mid):
        self.id = mid


class _FakeClient:
    """Records the ordered send stream; hands out increasing message ids."""

    def __init__(self, *, username="new_index"):
        self.username = username
        self.events: list[tuple[str, object]] = []
        self.pins: list[int] = []
        self._next_id = 7000

    async def get_chat(self, chat_id):
        return SimpleNamespace(id=chat_id, username=self.username)

    async def send_sticker(self, chat_id, sticker):
        self._next_id += 1
        self.events.append(("sticker", sticker))
        return _FakeMsg(self._next_id)

    async def send_photo(self, chat_id, image, caption=None, reply_markup=None, parse_mode=None):
        self._next_id += 1
        self.events.append(("photo", {"caption": caption}))
        return _FakeMsg(self._next_id)

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self._next_id += 1
        self.events.append(("message", {"caption": text}))
        return _FakeMsg(self._next_id)

    async def pin_chat_message(self, chat_id, mid, disable_notification=False):
        self.pins.append(mid)

    async def edit_message_caption(self, chat_id, mid, caption=None, parse_mode=None, reply_markup=None):
        return _FakeMsg(mid)


def _container(sessionmaker, client=None):
    return SimpleNamespace(
        pg_sessionmaker=sessionmaker,
        admin_client=client,
        collections=None,
        config=SimpleNamespace(
            index_channel=IndexChannelConfig(
                enabled=True, channel_id=-100500, username="old_index",
                poster_message_id=171,
            ),
            main_channel=SimpleNamespace(divider_sticker_id=""),
            bot=SimpleNamespace(divider_sticker_id="DIV"),
        ),
    )


async def _seed_index(sessionmaker):
    """Two labelled sections (A, B) + one reserved slot + a title under A."""
    async with sessionmaker() as s:
        s.add(StoragePack(anime_title="Attack on Titan", anime_doc_id="a1",
                          season=1, resolution="1080p", audio="subbed",
                          channel_id=-100500, start_message_id=1, end_message_id=2))
        s.add_all([
            IndexSection(sort_order=1, label="A", base_letter="A", message_id=10),
            IndexSection(sort_order=2, label="B", base_letter="B", message_id=11),
            IndexSection(sort_order=3, label=None, base_letter=None, message_id=12),
        ])
        await s.commit()


async def test_record_index_captures_poster_and_all_slots(session, sessionmaker, monkeypatch):
    _stub_mirror(monkeypatch)
    await _seed_index(sessionmaker)
    svc = BackupService(_container(sessionmaker, _FakeClient()))

    row = await svc.record_index()

    assert row is not None and row.scope == "index"
    kinds = [c["kind"] for c in row.cards]
    # Poster first (pinned), then the two letter sections, then the reserved slot.
    assert kinds == ["index_poster", "index_section", "index_section", "index_reserved"]
    assert row.cards[0]["is_pinned"] is True
    # Slots carry their original sort_order so restore can remap message ids.
    assert [c.get("sort_order") for c in row.cards[1:]] == [1, 2, 3]
    # Reserved slot keeps its "Slot n/total" caption (so it stays recognisable).
    assert "Slot 1/1" in row.cards[3]["caption"]


async def test_restore_index_reposts_remaps_and_repoints(session, sessionmaker, monkeypatch):
    _stub_mirror(monkeypatch)
    await _seed_index(sessionmaker)
    client = _FakeClient(username="new_index")
    svc = BackupService(_container(sessionmaker, client))
    await svc.record_index()

    stats = await svc.restore_index(-100999, new_username="new_index")

    # Poster + 2 sections + 1 reserved = 4 slots restored.
    assert stats.total == 4 and stats.restored == 4 and stats.failed == 0
    # The poster was pinned on the fresh channel.
    assert len(client.pins) == 1
    # Every IndexSection now points at a freshly-posted message id (> seed ids).
    async with sessionmaker() as s:
        secs = (await s.execute(
            select(IndexSection).order_by(IndexSection.sort_order)
        )).scalars().all()
    assert all(sec.message_id > 100 for sec in secs)
    # Config repointed to the new channel + username.
    assert svc.cfg_index.channel_id == -100999
    assert svc.cfg_index.username == "new_index"
    assert svc.cfg_index.poster_message_id is not None


async def test_restore_index_no_backup_is_noop(session, sessionmaker):
    client = _FakeClient()
    svc = BackupService(_container(sessionmaker, client))
    stats = await svc.restore_index(-100999)
    assert stats.total == 0 and stats.restored == 0
    assert client.events == []


def _stub_mirror(monkeypatch):
    """Offline, deterministic image mirroring for both byte and url paths."""
    import kurosoden.shared.image_backup as ib

    async def fake_backup_bytes(container, blob, *, mime="image/jpeg", source_url=""):
        return BackupImage(source_url=source_url, catbox_url="mir/letter.jpg")

    async def fake_backup_image(container, url):
        return BackupImage(source_url=url, catbox_url=f"mir/{url.rsplit('/', 1)[-1]}")

    monkeypatch.setattr(ib, "backup_bytes", fake_backup_bytes)
    monkeypatch.setattr(ib, "backup_image", fake_backup_image)
