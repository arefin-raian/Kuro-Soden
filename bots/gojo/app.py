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
from kage.shared.ui_helpers import reply_with_screen

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

    # ── Catch-all menu callback ─────────────────────────────────────────────
    # Inline buttons on /start route to `gojo|<action>`. Whatever doesn't
    # match a real handler gets a one-line alert rather than silent failure.
    from pyrogram.types import CallbackQuery

    @client.on_callback_query(filters.regex(r"^gojo\|"))
    async def _gojo_menu_fallback(_: Client, q: CallbackQuery) -> None:
        # Inline-query-based callbacks can have q.message=None (callback
        # via an inline keyboard never has it, but Pyrogram types lie) —
        # skip silently rather than dereferencing q.message.chat.id below.
        if q.message is None:
            await q.answer()
            return
        try:
            _, action = q.data.split("|", 1)
        except ValueError:
            action = "help"
        await q.answer(f"Type /{action} in chat.", show_alert=False)
        try:
            await reply_with_screen(
                client, q.message.chat.id,
                f"<b>📍 Type /{action} in chat.</b>",
                bot_name="gojo", old_msg=q.message,
            )
        except Exception as exc:
            log.warning(
                "menu_fallback.screen_failed",
                bot="gojo", action=action, error=str(exc),
            )

    # ── /start ────────────────────────────────────────────────────────────────
    # Rich UI: sticker → loading animation → welcome screen with inline keyboard
    # and Gojo-themed artwork (images/gojo/).
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen
        from nekofetch.ui.components import cb, keyboard
        from nekofetch.ui.artwork import pick_artwork
        from kage.shared.ui_helpers import send_rich_welcome

        rows = [
            [("📋 Tasks", cb("gojo", "tasks")),
             ("🔮 Publish", cb("gojo", "publish"))],
            [("📅 Schedule", cb("gojo", "schedule")),
             ("🛡 Recover", cb("gojo", "recover"))],
            [("⚙️ Settings", cb("gojo", "settings")),
             ("❓ Help", cb("misc", "help"))],
        ]
        screen = Screen(
            caption=(
                "<b>🔮 Gojo Satoru — Publisher</b>\n\n"
                "<i>\"Throughout heaven and earth, I alone am the honored one.\"</i>\n\n"
                "I handle the final step:\n"
                "• Generate main channel posts\n"
                "• Create franchise thumbnails\n"
                "• Review and edit captions\n"
                "• Publish or schedule\n"
                "• Update the index\n"
                "• Recover banned channels"
            ),
            image=pick_artwork("gojo"),
            keyboard=keyboard(*rows),
        )
        await send_rich_welcome(client, container, message, screen)

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
            image=pick_artwork("gojo"),
        )
        await send_screen(client, message.chat.id, screen)

    return client
