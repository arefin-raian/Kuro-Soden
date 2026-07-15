"""Senku — Distribution Bot (科学の使者 · The Science Messenger).

Handles:
  • Channel creation guidance for admins.
  • TMDB poster → profile picture prompt.
  • Auto-generate: info card, stickers, season separators, watch guide, footer.
  • Season thumbnail generation (posters, logos, layouts).
  • Per-bot settings panel.

Reuses NekoFetch's BotContentService + BotFactory for all content generation.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from kage.shared.ui_helpers import reply_with_screen

SENKU_COMMANDS = [
    BotCommand("start", "View your assigned distribution tasks"),
    BotCommand("tasks", "List active distribution tasks"),
    BotCommand("create", "Create a new distribution channel"),
    BotCommand("generate", "Generate content: /generate REQ-XXXX"),
    BotCommand("settings", "Configure the distribution bot"),
    BotCommand("help", "How distribution works"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(SENKU_COMMANDS)


def build_senku(container: Container, token: str) -> Client:
    """Build and wire the Senku (Distribution) bot client.

    All task/generate/create handlers are registered via ``register_all``.
    """
    client = Client(
        name="kage-senku",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    from kage.bots.senku.handlers import register_all
    register_all(client, container)

    # ── Catch-all menu callback ─────────────────────────────────────────────
    # Inline buttons on /start route to `senku|<action>`. Whatever doesn't
    # match a real handler gets a one-line alert rather than silent failure.
    from pyrogram.types import CallbackQuery

    @client.on_callback_query(filters.regex(r"^senku\|"))
    async def _senku_menu_fallback(_: Client, q: CallbackQuery) -> None:
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
                bot_name="senku", old_msg=q.message,
            )
        except Exception as exc:
            log.warning(
                "menu_fallback.screen_failed",
                bot="senku", action=action, error=str(exc),
            )

    # ── /start ────────────────────────────────────────────────────────────────
    # Rich UI: sticker → loading animation → welcome screen with inline keyboard
    # and Senku-themed artwork (images/senku/).
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen
        from nekofetch.ui.components import cb, keyboard
        from nekofetch.ui.artwork import pick_artwork
        from kage.shared.ui_helpers import send_rich_welcome

        rows = [
            [("📋 Tasks", cb("senku", "tasks")),
             ("🧪 Generate", cb("senku", "generate"))],
            [("📢 Create Channel", cb("senku", "create"))],
            [("⚙️ Settings", cb("senku", "settings")),
             ("❓ Help", cb("misc", "help"))],
        ]
        screen = Screen(
            caption=(
                "<b>🧪 Senku Ishigami — Distribution</b>\n\n"
                "<i>\"Ten billion percent — this channel will be perfect.\"</i>\n\n"
                "I handle distribution:\n"
                "• Guide channel creation\n"
                "• Generate info cards & stickers\n"
                "• Create season separators & watch guides\n"
                "• Add footers and branding"
            ),
            image=pick_artwork("senku"),
            keyboard=keyboard(*rows),
        )
        await send_rich_welcome(client, container, message, screen)

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen
        from nekofetch.ui.components import cb, keyboard

        screen = Screen(
            caption="<b>⚙️ Senku Settings</b>\n\n"
                     "Configure distribution preferences and branding.",
            keyboard=keyboard(
                [("Branding", cb("senku", "set", "branding")),
                 ("Content Layout", cb("senku", "set", "layout"))],
                [("Back", cb("senku", "home"))],
            ),
            image=pick_artwork("senku"),
        )
        await send_screen(client, message.chat.id, screen)

    return client
