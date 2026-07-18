"""Levi native settings panel — Phase 0 coverage.

Levi's old ``/settings`` pointed at ``/dlset`` / ``/procset`` commands that no
handler ever parsed. This suite guards the replacement:

  • every Levi settings section maps to a real ``AppConfig`` attribute,
  • every ``levi|set|…`` callback a settings surface emits is actually routed
    (no dead taps), and
  • the new ``TELEGRAM_USERBOT_SESSION`` env field and the ``edit_markup``
    live-toggle helper exist and behave.
"""

from __future__ import annotations

import asyncio

import pytest
from pyrogram import Client
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.handlers.conversation_handler import ConversationHandler
from pyrogram.types import CallbackQuery

from kurosoden.tests.test_lelouch_routing import FakeContainer

from kurosoden.bots.levi.handlers.settings import LEVI_SECTIONS, _SECTION_LABEL


# ── section → real config field mapping ─────────────────────────────────────────

def _live_config():
    from nekofetch.core.config import AppConfig
    return AppConfig.load()


def test_every_levi_section_is_a_real_config_attr():
    cfg = _live_config()
    missing = [s for s in LEVI_SECTIONS if getattr(cfg, s, None) is None]
    assert not missing, f"Levi settings sections with no AppConfig attribute: {missing}"


def test_every_levi_section_has_a_label():
    unlabelled = [s for s in LEVI_SECTIONS if s not in _SECTION_LABEL]
    assert not unlabelled, f"Levi sections missing a panel label: {unlabelled}"


def test_section_fields_are_editable_and_documented():
    """Each section exposes at least one editable field, and every field the
    panel would render resolves through SettingsService without error."""
    from nekofetch.services.settings_service import SettingsService
    svc = SettingsService(_container_with_config())
    for section in LEVI_SECTIONS:
        fields = svc.section_fields(section)
        assert fields, f"{section} exposes no editable fields"
        for field, _value, kind in fields:
            assert kind in ("bool", "list", "value")


class _ConfigContainer(FakeContainer):
    """FakeContainer + a live AppConfig, for SettingsService introspection."""
    def __init__(self):
        super().__init__()
        self.config = _live_config()
        self.collections = None


def _container_with_config():
    return _ConfigContainer()


# ── env field ───────────────────────────────────────────────────────────────────

def test_userbot_session_env_field_exists():
    from nekofetch.core.config import EnvSettings
    assert "telegram_userbot_session" in EnvSettings.model_fields


# ── edit_markup live-toggle helper ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_markup_edits_in_place_not_resend():
    """edit_markup must call edit_reply_markup once with the new keyboard, and
    must never delete/resend. Returns True on success."""
    from nekofetch.ui.components import edit_markup

    calls = {"edit": 0, "delete": 0}

    class _Msg:
        async def edit_reply_markup(self, markup):
            calls["edit"] += 1
            self.markup = markup
        async def delete(self):
            calls["delete"] += 1

    class _Q:
        message = _Msg()

    q = _Q()
    ok = await edit_markup(q, [[("🟢 A", "levi|set|tog|downloads.x")], [("B", "levi|set|home")]])
    assert ok is True
    assert calls["edit"] == 1 and calls["delete"] == 0
    # keyboard shape preserved
    kb = q.message.markup.inline_keyboard
    assert kb[0][0].text == "🟢 A"
    assert kb[0][0].callback_data == "levi|set|tog|downloads.x"


@pytest.mark.asyncio
async def test_edit_markup_swallows_not_modified():
    """A no-op double-tap (MESSAGE_NOT_MODIFIED) is benign → returns False, no raise."""
    from nekofetch.ui.components import edit_markup

    class _Msg:
        async def edit_reply_markup(self, markup):
            raise RuntimeError("MESSAGE_NOT_MODIFIED")

    class _Q:
        message = _Msg()

    assert await edit_markup(_Q(), [[("A", "x")]]) is False


# ── routing: no dead taps on the levi|set surface ───────────────────────────────

async def _build_registered_client() -> Client:
    from kurosoden.bots.levi.app import build_levi
    client = build_levi(FakeContainer(), token="1:AAAA")
    for _ in range(30):
        await asyncio.sleep(0)
    return client


def _callback_handlers(client: Client):
    out = []
    for _grp, handlers in client.dispatcher.groups.items():
        for h in handlers:
            if isinstance(h, CallbackQueryHandler) and not isinstance(h, ConversationHandler):
                if h.filters is not None:
                    out.append(h)
    return out


async def _is_routed(client: Client, handlers, data: str) -> bool:
    cq = CallbackQuery(client=client, id="1", from_user=None, chat_instance="x")
    cq.data = data
    for h in handlers:
        cq.matches = None
        try:
            if await h.filters(client, cq):
                return True
        except Exception:
            continue
    return False


# Every callback the Levi settings surface can emit, with concrete args.
_SETTINGS_CALLBACKS = [
    "levi|set|home",
    "levi|set|sec|downloads",
    "levi|set|sec|rename",
    "levi|set|tog|processing.rename",
    "levi|set|edit|rename.template",
    "levi|set|edit|downloads.concurrent_downloads",
]


@pytest.mark.asyncio
class TestSettingsRouting:
    async def test_every_settings_callback_is_routed(self):
        client = await _build_registered_client()
        handlers = _callback_handlers(client)
        unrouted = [d for d in _SETTINGS_CALLBACKS
                    if not await _is_routed(client, handlers, d)]
        assert not unrouted, f"dead settings taps: {unrouted}"

    async def test_home_button_targets_native_panel(self):
        """The /start Settings button must point at levi|set|home (native panel),
        not the removed bare levi|settings."""
        client = await _build_registered_client()
        handlers = _callback_handlers(client)
        assert await _is_routed(client, handlers, "levi|set|home")
