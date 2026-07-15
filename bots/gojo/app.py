"""Gojo — Publisher Bot (最強の術師 · The Strongest Sorcerer).

Handles:
  • Main channel post generation.
  • Franchise thumbnail generation.
  • TMDB synopsis (not AniList) for descriptions.
  • Caption template → admin review → Markdown/HTML edit.
  • Publish (immediate or scheduled).
  • Index update.
  • Channel recovery tools (banned → replace → update all buttons).

Reuses NekoFetch's PublishingService, MainChannelService, IndexChannelService.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

GOJO_COMMANDS = [
    BotCommand("start", "View your assigned publishing tasks"),
    BotCommand("tasks", "List active publishing tasks"),
    BotCommand("publish", "Review and publish: /publish REQ-XXXX"),
    BotCommand("recover", "Recover a banned channel: /recover REQ-XXXX"),
    BotCommand("schedule", "Schedule a post for later"),
    BotCommand("settings", "Configure the publisher bot"),
    BotCommand("help", "How publishing works"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(GOJO_COMMANDS)


def build_gojo(container: Container, token: str) -> Client:
    """Build and wire the Gojo (Publisher) bot client.

    All publish/recover/schedule handlers are registered via ``register_all``.
    """
    client = Client(
        name="kage-gojo",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    from kage.bots.gojo.handlers import register_all
    register_all(client, container)

    # ── /start ────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen

        caption = (
            "<b>🔮 Gojo Satoru — Publisher</b>\n\n"
            "<i>\"Throughout heaven and earth, I alone am the honored one.\"</i>\n\n"
            "I handle the final step:\n"
            "• Generate main channel posts\n"
            "• Create franchise thumbnails\n"
            "• Review and edit captions\n"
            "• Publish or schedule\n"
            "• Update the index\n"
            "• Recover banned channels\n\n"
            "<b>Commands:</b>\n"
            "/tasks — Your tasks\n"
            "/publish — Review & publish\n"
            "/recover — Channel recovery\n"
            "/schedule — Schedule posts"
        )
        screen = Screen(caption=caption)
        await send_screen(client, message.chat.id, screen)

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen
        from nekofetch.ui.components import cb, keyboard

        screen = Screen(
            caption="<b>⚙️ Gojo Settings</b>\n\n"
                     "Configure publishing preferences and caption templates.",
            keyboard=keyboard(
                [("Caption Template", cb("gojo", "set", "caption")),
                 ("Main Channel", cb("gojo", "set", "main")),
                 ("Index Settings", cb("gojo", "set", "index"))],
                [("Back", cb("gojo", "home"))],
            ),
        )
        await send_screen(client, message.chat.id, screen)

    return client
