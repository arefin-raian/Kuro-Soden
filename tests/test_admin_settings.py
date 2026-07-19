"""Admin panel settings — routing + config-mapping coverage.

The admin bot's ``/settings`` control center used to be a bespoke
``handlers/settings.py`` that re-implemented the whole hub/section/edit surface
with raw presentation (bare slugs, ``{tokens}``, ``/command`` hints) — a second
copy of logic that already lived in :mod:`kurosoden.shared.settings_ui`. It now
delegates to that shared human-friendly engine, exactly like the four pipeline
bots. This suite guards the migration:

  • every admin settings section maps to a real ``AppConfig`` attribute,
  • every ``admin|set|…`` callback the settings surface emits is actually routed
    (no dead taps), and the admin-home Settings button lands on the shared hub,
  • the retired ``settings|…`` namespace is gone (no lingering emitters).
"""

from __future__ import annotations

import asyncio

import pytest
from pyrogram import Client
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.handlers.conversation_handler import ConversationHandler
from pyrogram.types import CallbackQuery

from kurosoden.tests.test_lelouch_routing import FakeContainer
from nekofetch.bots.admin.handlers.settings import _SETTINGS_ORDER


# ── section → real config field mapping ──────────────────────────────────────

def _live_config():
    from nekofetch.core.config import AppConfig
    return AppConfig.load()


def test_admin_sections_map_to_real_config_attrs():
    """Every section the admin hub lists must exist on AppConfig — otherwise the
    shared engine silently drops it and the button dead-ends. (localization may
    be absent on some builds; the engine drops it gracefully, so it's exempt.)"""
    cfg = _live_config()
    missing = [s for s in _SETTINGS_ORDER
               if s != "localization" and getattr(cfg, s, None) is None]
    assert not missing, f"admin settings sections with no AppConfig attribute: {missing}"


# ── routing: no dead taps on the admin|set surface ───────────────────────────

class _ConfigContainer(FakeContainer):
    """FakeContainer + a live AppConfig, so the shared engine can introspect the
    sections during registration."""
    def __init__(self):
        super().__init__()
        self.config = _live_config()
        self.collections = None


async def _build_client() -> Client:
    """A bare Pyrogram client with only the admin settings surface registered.

    We register the module directly rather than the full admin bot: the whole bot
    pulls in dozens of handlers needing live services, but the settings routing is
    self-contained and is what this suite is about.
    """
    from nekofetch.bots.admin.handlers.settings import register

    client = Client("test-admin", api_id=1, api_hash="0" * 32, in_memory=True)
    register(client, _ConfigContainer())
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


# Every callback the admin settings surface can emit, with concrete args.
_SETTINGS_CALLBACKS = [
    "admin|settings",                               # /start + admin-home button
    "admin|set|home",                               # Back-from-section
    "admin|set|sec|downloads",
    "admin|set|sec|features",
    "admin|set|tog|processing.verify_files",        # toggle
    "admin|set|edit|downloads.concurrent_downloads",  # free-text edit
    "admin|set|pick|features.some_enum",            # choice picker open
    "admin|set|opt|features.some_enum|value",       # choice picker set
]

# Callbacks the admin *home* emits — must still route after the migration.
_HOME_CALLBACKS = [
    "admin|home", "admin|analytics", "queue|view|0",
]


@pytest.mark.asyncio
class TestAdminSettingsRouting:
    async def test_every_settings_callback_is_routed(self):
        client = await _build_client()
        handlers = _callback_handlers(client)
        unrouted = [d for d in _SETTINGS_CALLBACKS
                    if not await _is_routed(client, handlers, d)]
        assert not unrouted, f"dead settings taps: {unrouted}"

    async def test_home_and_dashboard_callbacks_still_route(self):
        client = await _build_client()
        handlers = _callback_handlers(client)
        unrouted = [d for d in _HOME_CALLBACKS
                    if not await _is_routed(client, handlers, d)]
        assert not unrouted, f"admin home/dashboard taps broke: {unrouted}"

    async def test_retired_settings_namespace_is_dead(self):
        """The old bespoke panel used the ``settings|…`` namespace. Nothing should
        route it any more — the migration replaced it with ``admin|set|…``."""
        client = await _build_client()
        handlers = _callback_handlers(client)
        for dead in ("settings|home", "settings|sec|downloads",
                     "settings|tog|processing.verify_files"):
            assert not await _is_routed(client, handlers, dead), \
                f"old settings namespace still routed: {dead}"
