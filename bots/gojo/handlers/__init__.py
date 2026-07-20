"""Gojo handler registration.

Reuses NekoFetch's existing publishing infrastructure:
  • MainChannelService — generates and posts to the main channel.
  • IndexChannelService — updates the A-Z index.
  • PublishingService — orchestrates the publish flow.
  • BotOrchestratorService — handles bot recreation for recovery.
"""

from __future__ import annotations

from pyrogram import Client
from nekofetch.core.container import Container


def register_all(client: Client, container: Container) -> None:
    from nekofetch.bots.middleware import install_auth_middleware
    from nekofetch.ui.components import cb
    from kurosoden.bots.gojo.handlers.tasks import register as register_tasks
    from kurosoden.shared.settings_ui import register_settings
    from kurosoden.shared.timezone_ui import register_timezone_ui

    install_auth_middleware(client, container)
    register_tasks(client, container)

    # Per-admin timezone picker ("🌍 My Timezone"). Lives outside config because
    # timezone is a property of the person, not the bot — it drives how each admin
    # types/reads scheduled-post times. Its free-text capture uses its own message
    # group so it doesn't fight the settings editor or the task FSM.
    register_timezone_ui(client, container, "gojo")

    # Human-friendly settings — Gojo owns the public-facing channels: the main
    # channel caption, the A–Z index, and the thumbnail channel. Registered
    # before the app.py `gojo|` fallback so every `gojo|set|…` tap lands here.
    register_settings(
        client, container, "gojo",
        ["main_channel", "index_channel", "thumbnail_channel"],
        title="Gojo — Publishing Settings",
        blurb=(
            "How every public post reads — the main-channel caption, the A–Z "
            "index lines, and the thumbnail channel. Edit a template and you'll "
            "see a live preview filled with a real example before you save."
        ),
        extra_buttons=[("🌍 My Timezone", cb("gojo", "tz", "home"))],
    )
