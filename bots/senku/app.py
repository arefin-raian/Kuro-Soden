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

    # ── /start ────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen

        caption = (
            "<b>🧪 Senku Ishigami — Distribution</b>\n\n"
            "<i>\"Ten billion percent — this channel will be perfect.\"</i>\n\n"
            "I handle distribution:\n"
            "• Guide channel creation\n"
            "• Generate info cards & stickers\n"
            "• Create season separators & watch guides\n"
            "• Add footers and branding\n\n"
            "<b>Commands:</b>\n"
            "/tasks — Your tasks\n"
            "/create — New channel setup\n"
            "/generate — Generate content\n"
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
            caption="<b>⚙️ Senku Settings</b>\n\n"
                     "Configure distribution preferences and branding.",
            keyboard=keyboard(
                [("Branding", cb("senku", "set", "branding")),
                 ("Content Layout", cb("senku", "set", "layout"))],
                [("Back", cb("senku", "home"))],
            ),
        )
        await send_screen(client, message.chat.id, screen)

    return client
