"""Levi — Downloader Bot (人類最強の兵士 · Humanity's Strongest Soldier).

Handles:
  • Manual source selection (admin picks the source — no auto-fallback).
  • Download execution via NekoFetch's existing download pipeline.
  • File processing (rename, brand, caption, metadata).
  • Manual thumbnail upload (1:1 square image).
  • Header generation with Markdown/HTML edit approval.
  • Multi-season / OVA / Movie / Franchise support.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

LEVI_COMMANDS = [
    BotCommand("start", "View your assigned download tasks"),
    BotCommand("tasks", "List active and pending tasks"),
    BotCommand("assign", "Assign source: /assign REQ-XXXX source_name"),
    BotCommand("sources", "Browse available download sources"),
    BotCommand("header", "Generate header: /header REQ-XXXX"),
    BotCommand("settings", "Configure the downloader bot"),
    BotCommand("help", "How the downloader works"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(LEVI_COMMANDS)


def build_levi(container: Container, token: str) -> Client:
    """Build and wire the Levi (Downloader) bot client.

    All task/source/thumbnail/header handlers are registered via
    ``register_all`` in handlers/ — this keeps app.py clean.
    """
    client = Client(
        name="kage-levi",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    # Register all handlers (middleware + tasks).
    from kage.bots.levi.handlers import register_all

    register_all(client, container)

    # ── /start ────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen

        caption = (
            "<b>⚔️ Levi Ackerman — Downloader</b>\n\n"
            "<i>\"No task is impossible. Only tasks I haven't cut down yet.\"</i>\n\n"
            "I handle the download pipeline:\n"
            "• Select the source manually\n"
            "• Download and process files\n"
            "• Upload thumbnails and generate headers\n\n"
            "<b>Commands:</b>\n"
            "/tasks — Your assigned tasks\n"
            "/sources — Available sources\n"
            "/assign — Assign source + queue download\n"
            "/header — Generate header\n"
            "/settings — Configuration"
        )
        screen = Screen(caption=caption)
        await send_screen(client, message.chat.id, screen)

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen
        from nekofetch.ui.components import cb, keyboard

        screen = Screen(
            caption="<b>⚙️ Levi Settings</b>\n\n"
                     "Configure download preferences and pipeline options.",
            keyboard=keyboard(
                [("Download Settings", cb("levi", "set", "downloads")),
                 ("Processing Options", cb("levi", "set", "processing"))],
                [("Back", cb("levi", "home"))],
            ),
        )
        await send_screen(client, message.chat.id, screen)

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        await message.reply(
            "<b>⚔️ Levi — Downloader Bot</b>\n\n"
            "<b>How it works:</b>\n"
            "1. View your tasks with /tasks\n"
            "2. Pick a source from /sources\n"
            "3. Assign with /assign REQ-XXXX source_name\n"
            "4. I queue it — NekoFetch's DownloadWorker handles the rest\n"
            "5. Upload a 1:1 square thumbnail\n"
            "6. Generate the header with /header REQ-XXXX\n\n"
            "<b>The download is automatic after you assign a source — "
            "you don't need to do anything else!</b>",
            parse_mode=ParseMode.HTML,
        )

    return client
