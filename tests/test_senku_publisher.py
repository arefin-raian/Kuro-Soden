"""Tests for kurosoden/shared/senku_publisher.py — the Phase 4 channel poster.

Covers the two pure transforms that make the publisher honour the admin's work
without touching Telegram, catbox, or AniList:

  • ``_reorder_franchise`` re-emits a fresh AniList walk in the *confirmed*
    cached order, splits TV vs extras, and drops entries the admin removed.
  • ``_build_buttons`` renders URL-only keyboards from ``button_data.links``
    (flat + separate-audio), and never emits a button without a link.
  • ``_send_posts`` resolves ``{BOT_QUAL:...}`` captions, drops dividers between
    sections, and pins the info card + watch guide — all against a fake client.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from kurosoden.shared.distribution_cache import EntryData
from kurosoden.shared.senku_publisher import SenkuPublisher


@dataclass
class _FE:
    """Stand-in for AnilistClient.FranchiseEntry (only the fields we read)."""
    anilist_id: int
    format: str
    english_title: str = "X"


class _FakeContainer:
    redis = None


@pytest.fixture
def pub():
    return SenkuPublisher(_FakeContainer())


# ── _reorder_franchise ───────────────────────────────────────────────────────────

def _walk():
    return {
        "tv": [_FE(101, "TV"), _FE(102, "TV")],
        "extras": [_FE(201, "MOVIE"), _FE(202, "OVA")],
        "all": [_FE(101, "TV"), _FE(102, "TV"), _FE(201, "MOVIE"), _FE(202, "OVA")],
    }


def test_reorder_follows_confirmed_order(pub):
    # Admin confirmed: movie first, then S2, then S1 — a deliberate reshuffle.
    entries = [
        EntryData(index=1, label="Movie", kind="movie", anilist_id=201),
        EntryData(index=2, label="Season 2", kind="season", anilist_id=102),
        EntryData(index=3, label="Season 1", kind="season", anilist_id=101),
    ]
    out = pub._reorder_franchise(_walk(), entries)
    assert [e.anilist_id for e in out["all"]] == [201, 102, 101]
    # Split respects the reshuffle: TV entries keep confirmed order.
    assert [e.anilist_id for e in out["tv"]] == [102, 101]
    assert [e.anilist_id for e in out["extras"]] == [201]


def test_reorder_drops_removed_entries(pub):
    # Admin kept only one entry; the rest of the walk is discarded.
    entries = [EntryData(index=1, label="Season 1", kind="season", anilist_id=101)]
    out = pub._reorder_franchise(_walk(), entries)
    assert [e.anilist_id for e in out["all"]] == [101]
    assert out["extras"] == []


def test_reorder_falls_back_when_no_ids(pub):
    # Bare franchise (cached entries carry no anilist_id): keep the walk order.
    entries = [EntryData(index=1, label="Season 1", kind="season", anilist_id=None)]
    out = pub._reorder_franchise(_walk(), entries)
    assert [e.anilist_id for e in out["all"]] == [101, 102, 201, 202]


# ── _build_buttons ─────────────────────────────────────────────────────────────

def test_flat_buttons_only_emit_linked_qualities(pub):
    bd = {"type": "flat", "qualities": ["480p", "720p", "1080p"],
          "links": {"480p": "https://t.me/f?a", "1080p": "https://t.me/f?c"}}
    markup = pub._build_buttons(bd)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    # 720p has no link, so it's dropped.
    assert labels == ["480p", "1080p"]
    assert all(b.url for row in markup.inline_keyboard for b in row)


def test_buttons_none_without_links(pub):
    assert pub._build_buttons({"type": "flat", "qualities": ["480p"], "links": {}}) is None
    assert pub._build_buttons(None) is None


def test_separate_audio_buttons(pub):
    bd = {
        "type": "separate_audio",
        "sections": [
            {"language": "sub", "qualities": ["720p"]},
            {"language": "dub", "qualities": ["720p", "1080p"]},
        ],
        "links": {"sub_720p": "https://t.me/f?1", "dub_1080p": "https://t.me/f?2"},
    }
    markup = pub._build_buttons(bd)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    # dub_720p has no link → dropped; the rest survive.
    assert labels == ["720p", "1080p"]


# ── _send_posts (fake client) ────────────────────────────────────────────────────

class _FakeChat:
    username = "aot_channel"


class _FakeMsg:
    def __init__(self, mid):
        self.id = mid
        self.pinned_message = None


class _FakeClient:
    def __init__(self):
        self.photos = []
        self.messages = []
        self.stickers = []
        self.pinned = []
        self._next_id = 100

    async def get_chat(self, chat_id):
        return _FakeChat()

    async def send_sticker(self, chat_id, sticker):
        self.stickers.append(sticker)

    async def send_photo(self, chat_id, image, caption=None, reply_markup=None, parse_mode=None):
        self._next_id += 1
        self.photos.append(caption)
        return _FakeMsg(self._next_id)

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self._next_id += 1
        self.messages.append(text)
        return _FakeMsg(self._next_id)

    async def pin_chat_message(self, chat_id, message_id, disable_notification=True):
        self.pinned.append(message_id)

    async def get_messages(self, chat_id, mid):
        return _FakeMsg(mid)

    async def delete_messages(self, chat_id, mid):
        pass


@pytest.mark.asyncio
async def test_send_posts_dividers_pins_and_qual(pub):
    client = _FakeClient()

    class _Cfg:
        class bot:
            divider_sticker_id = "DIV"
    pub._c.config = _Cfg()

    posts = [
        {"post_type": "info_card", "caption": "Info", "image": "u1",
         "button_data": None, "pinned": True},
        {"post_type": "season_card",
         "caption": "Watch on {BOT_QUAL:720p}", "image": "u2",
         "button_data": None, "pinned": False},
        {"post_type": "watch_guide", "caption": "Guide", "image": None,
         "button_data": None, "pinned": True},
    ]
    posted, pinned = await pub._send_posts(client, -100123, posts)

    assert posted == 3
    # Info + guide pinned (two ids), season card not.
    assert len(pinned) == 2 and len(client.pinned) == 2
    # Dividers: one between each of the 3 posts → 2 stickers.
    assert client.stickers == ["DIV", "DIV"]
    # {BOT_QUAL:720p} resolved to a link on the channel handle.
    assert any('href="https://t.me/aot_channel"' in c and ">720p<" in c
               for c in client.photos)


@pytest.mark.asyncio
async def test_send_posts_survives_a_failed_card(pub):
    client = _FakeClient()

    async def _boom(*a, **k):
        raise RuntimeError("telegram down")
    client.send_photo = _boom

    class _Cfg:
        class bot:
            divider_sticker_id = None
    pub._c.config = _Cfg()

    posts = [
        {"post_type": "info_card", "caption": "Info", "image": "u1",
         "button_data": None, "pinned": True},
        {"post_type": "footer", "caption": "Footer", "image": None,
         "button_data": None, "pinned": False},
    ]
    posted, pinned = await pub._send_posts(client, -100123, posts)
    # The photo card failed; the text footer still posted.
    assert posted == 1
    assert client.messages == ["Footer"]
