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
    from kurosoden.shared.menu_router import settings_hub, settings_onboarding, tool_screen
    from kurosoden.shared.settings_content import ALL_BY_BOT
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
                [InlineKeyboardButton("📋 Tasks", callback_data=cb(bot, "tasks")),
                 InlineKeyboardButton("🌐 Sources", callback_data=cb(bot, "sources"))],
                [InlineKeyboardButton("🎯 Assign", callback_data=cb(bot, "assign")),
                 InlineKeyboardButton("📝 Header", callback_data=cb(bot, "header"))],
                [InlineKeyboardButton("⚙️ Settings", callback_data=cb(bot, "settings"))],
            ])
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Tool panels ¬¬
        if action in ("tasks", "sources", "assign", "header"):
            titles = {"tasks": "📋 Your Tasks",
                      "sources": "🌐 Source Browser",
                      "assign": "🎯 Assign a Source",
                      "header": "📝 Generate Header"}
            body_map = {
                "tasks": [
                    "Everything assigned to you, newest first.",
                    "",
                    f"  {BULLET} Each card shows the anime, its code, and where it is in the pipeline.",
                    f"  {BULLET} Tap a task to open it and pick a source.",
                    "<blockquote>Requests are routed here automatically — the queue hands each one to whoever's free.</blockquote>",
                ],
                "sources": [
                    "Where the episodes come from. You choose — nothing is picked for you.",
                    "",
                    f"  {BULLET} <b>Website</b> — full episode reports, sub &amp; dub coverage compared side by side.",
                    f"  {BULLET} <b>Torrent</b> — seeder-ranked, dual-audio first; may need re-encoding.",
                    f"  {BULLET} <b>Telegram (manual)</b> — you drop in the files and name them yourself.",
                    "<blockquote>Open a task to see a live report before you commit to one.</blockquote>",
                ],
                "assign": [
                    "Point a task at a source and start the download.",
                    "",
                    f"  {BULLET} Open a task from <b>Tasks</b>.",
                    f"  {BULLET} Read the source report, then tap the source you want.",
                    f"  {BULLET} Pick which franchise entries to pull, and it queues on its own.",
                    "<blockquote>No codes to type — the whole flow is buttons.</blockquote>",
                ],
                "header": [
                    "The main-channel header card for a finished title.",
                    "",
                    f"  {BULLET} Built from the franchise art and metadata already on file.",
                    f"  {BULLET} Preview it, then approve or tweak before it publishes.",
                    "<blockquote>Open a completed task to generate its header.</blockquote>",
                ],
            }
            caption, keyboard = tool_screen(
                bot, title=titles[action],
                kicker="Everything here runs on taps — no commands to memorize.",
                lines=body_map[action],
                back="home",
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Settings hub ¬¬
        if action == "settings":
            caption, keyboard = settings_hub(
                bot, title="Levi Settings",
                body=("Configure download concurrency, retry behavior, and the "
                      "post-download processing pipeline.\n\n"
                      "<i>Tap a row to open the help panel for that key, then "
                      "send the new value as a chat message.</i>"),
                items=[("Download Settings", "downloads"),
                       ("Processing Options", "processing")],
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ set|<key> onboarding ¬¬
        if action == "set" and arg:
            info = ALL_BY_BOT.get(bot, {}).get(arg)
            if info:
                caption, keyboard = settings_onboarding(
                    bot, arg, title=info["title"], about=info["about"],
                    when_to_use=info.get("when_to_use", ""),
                    options=info.get("options"),
                    placeholders=info.get("placeholders"),
                    supports_html=info.get("supports_html", False),
                    example=info.get("example", ""),
                    danger=info.get("danger", ""),
                    hint=info.get("hint", "Send the new value as a chat message."),
                )
                await send_screen(client, q.message.chat.id,
                                  Screen(caption=caption, image=pick_artwork(bot),
                                         keyboard=keyboard), old_msg=q.message)
                await q.answer()
                return

        # ¬¬ Help ¬¬
        if action == "help":
            caption, keyboard = tool_screen(
                bot, title="❓ Levi — Help",
                kicker="Everything the downloader can do.",
                lines=[
                    "I run the <b>download</b> stage of the pipeline.",
                    "",
                    "<b>📋 Tasks</b> — jobs assigned to you, with live stage icons.",
                    "<b>🌐 Sources</b> — browse providers and pick one per title.",
                    "<b>🎯 Assign</b> — bind a source to a task, then the worker runs it.",
                    "<b>📝 Header</b> — render the main-channel header from metadata.",
                    "",
                    "Everything here is a button — no command memorising needed.",
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
            [("📋 Tasks", cb("levi", "tasks")),
             ("🌐 Sources", cb("levi", "sources"))],
            [("🎯 Assign", cb("levi", "assign")),
             ("📝 Header", cb("levi", "header"))],
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
        await send_rich_welcome(client, container, message, screen)

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
            image=pick_artwork("levi"),
        )
        await send_screen(client, message.chat.id, screen)

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        caption = (
            "<b>⚔️ Levi — Downloader Bot</b>\n\n"
            "<b>How it works:</b>\n"
            "1. View your tasks with /tasks\n"
            "2. Pick a source from /sources\n"
            "3. Assign with /assign REQ-XXXX source_name\n"
            "4. I queue it — NekoFetch's DownloadWorker handles the rest\n"
            "5. Upload a 1:1 square thumbnail\n"
            "6. Generate the header with /header REQ-XXXX\n\n"
            "<b>The download is automatic after you assign a source — "
            "you don't need to do anything else!</b>"
        )
        from nekofetch.ui.components import cb, keyboard
        await reply_with_screen(
            client, message.chat.id, caption, bot_name="levi",
            keyboard=keyboard([("⬅ Back", cb("levi", "home"))]),
        )

    return client
