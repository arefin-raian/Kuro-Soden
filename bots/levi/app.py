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

from nekofetch.core.constants import BULLET
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from kurosoden.shared.ui_helpers import reply_with_screen
from nekofetch.ui.artwork import pick_artwork

LEVI_COMMANDS = [
    BotCommand("start", "View your assigned download tasks"),
    BotCommand("tasks", "Open your download tasks and pick a source"),
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
        name="kurosoden-levi",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    # Register all handlers (middleware + tasks).
    from kurosoden.bots.levi.handlers import register_all

    register_all(client, container)

    # ── Catch-all menu callback ─────────────────────────────────────────────
    # Inline buttons on /start route to `levi|<action>`. The dispatcher below
    # maps every action to a real screen — no more "Type /X in chat" toasts.
    from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                                InlineKeyboardMarkup)
    from kurosoden.shared.menu_router import tool_screen
    from nekofetch.ui.components import cb
    from nekofetch.ui.screens import Screen, send_screen

    @client.on_callback_query(filters.regex(r"^levi\|"))
    async def _levi_menu_fallback(client: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        parts = q.data.split("|", 2)
        action = parts[1] if len(parts) > 1 else "home"
        arg = parts[2] if len(parts) > 2 else ""
        bot = "levi"

        # ¬¬ Home ¬¬
        if action == "home":
            caption = (
                "<b>⚔️ Levi Ackerman — Downloader</b>\n\n"
                "<i>\"No task is impossible. Only tasks I haven't cut down yet.\"</i>\n\n"
                "I handle the download pipeline:\n"
                "• Select the source manually\n"
                "• Download and process files\n"
                "• Upload thumbnails and generate headers"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Tasks", callback_data=cb(bot, "tasks"))],
                [InlineKeyboardButton("⚙️ Settings", callback_data=cb(bot, "set", "home")),
                 InlineKeyboardButton("❓ Help", callback_data=cb(bot, "help"))],
            ])
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Tool panels ¬¬
        # NOTE: "tasks" is handled by handlers/tasks.py (levi|tasks) — it renders
        # the live assigned-task list that routes into the shared download flow.
        # Only the static "how sourcing works" panel lives here now.
        if action == "sources":
            caption, keyboard = tool_screen(
                bot, title="🌐 How Sourcing Works",
                kicker="Open a task and you'll choose one of these per title.",
                lines=[
                    "You pick where every title comes from — nothing is auto-chosen.",
                    "",
                    f"  {BULLET} <b>Website</b> — full episode reports, sub &amp; dub coverage compared side by side.",
                    f"  {BULLET} <b>Torrent</b> — seeder-ranked, dual-audio first; may need re-encoding.",
                    f"  {BULLET} <b>Telegram (manual)</b> — you drop in the files and name them yourself.",
                    "<blockquote>Open a task from <b>📋 Tasks</b> to see a live report before you commit.</blockquote>",
                ],
                back="home",
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Settings ¬¬
        # The real, config-driven settings panel lives in handlers/settings.py
        # under the `levi|set|…` namespace and is registered before this fallback,
        # so it handles every settings tap. The Home button points straight at
        # `levi|set|home`; nothing emits a bare `levi|settings` anymore.

        # ¬¬ Help ¬¬
        if action == "help":
            caption, keyboard = tool_screen(
                bot, title="❓ Levi — Help",
                kicker="Everything the downloader can do.",
                lines=[
                    "I run the <b>download</b> stage of the pipeline.",
                    "",
                    "<b>📋 Tasks</b> — jobs assigned to you. Tap one to open it.",
                    "",
                    "Opening a task walks you through everything:",
                    f"  {BULLET} pick a source (Website / Torrent / Telegram-manual),",
                    f"  {BULLET} read the coverage report or seeders list,",
                    f"  {BULLET} choose which franchise entries to pull.",
                    "",
                    "It queues on its own and the worker downloads + processes it.",
                    "Everything is a button — no commands to memorise.",
                ],
                back="home",
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        await q.answer(f"Action “{action}” not wired yet.", show_alert=True)

    # ── /start ────────────────────────────────────────────────────────────────
    # Rich UI: sticker → loading animation → welcome screen with inline keyboard
    # and Levi-themed artwork (images/levi/).
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen
        from nekofetch.ui.components import cb, keyboard
        from nekofetch.ui.artwork import pick_artwork
        from kurosoden.shared.ui_helpers import send_rich_welcome

        rows = [
            [("📋 Tasks", cb("levi", "tasks"))],
            [("🌐 How Sourcing Works", cb("levi", "sources"))],
            [("⚙️ Settings", cb("levi", "settings")),
             ("❓ Help", cb("levi", "help"))],
        ]
        screen = Screen(
            caption=(
                "<b>⚔️ Levi Ackerman — Downloader</b>\n\n"
                "<i>\"No task is impossible. Only tasks I haven't cut down yet.\"</i>\n\n"
                "I handle the download pipeline:\n"
                "• Select the source manually\n"
                "• Download and process files\n"
                "• Upload thumbnails and generate headers"
            ),
            image=pick_artwork("levi"),
            keyboard=keyboard(*rows),
        )
        await send_rich_welcome(client, container, message, screen, bot_name="levi")

    # ── /settings ─────────────────────────────────────────────────────────────
    # Opens the real, config-driven panel (handlers/settings.py). It introspects
    # the live AppConfig, so every download/rename/branding field is editable and
    # self-documenting — no dead `/dlset`-style commands.
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import send_screen
        from kurosoden.bots.levi.handlers.settings import build_home_screen

        await send_screen(client, message.chat.id, build_home_screen(container))

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        caption = (
            "<b>⚔️ Levi — Downloader Bot</b>\n\n"
            "<b>How it works:</b>\n"
            "1. Open your tasks with /tasks\n"
            "2. Tap a task to open it\n"
            "3. Pick a source — Website, Torrent, or Telegram-manual\n"
            "4. Read the coverage report, then choose franchise entries\n"
            "5. It queues automatically — the worker downloads + processes it\n\n"
            "<b>The whole flow is buttons — nothing to type after /tasks.</b>"
        )
        from nekofetch.ui.components import cb, keyboard
        await reply_with_screen(
            client, message.chat.id, caption, bot_name="levi",
            keyboard=keyboard([("⬅ Back", cb("levi", "home"))]),
        )

    return client
