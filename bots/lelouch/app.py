"""Lelouch Vi Britannia — Request Bot (影の司令官 · The Shadow Commander).

Handles:
  • User request intake — reuses NekoFetch's AniList search + franchise flow.
  • Duplicate detection before accepting (main channel → distribution → in-progress).
  • One-request-at-a-time limit for regular users.
  • Admin batch request support.
  • Admin assignment to the downloader stage.
  • Management features (availability, breaks, scheduling, reassignment).
  • Per-bot settings panel.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

LELOUCH_COMMANDS = [
    BotCommand("start", "Submit a new anime request"),
    BotCommand("myrequests", "View your request status"),
    BotCommand("help", "How requests work"),
    BotCommand("admin", "Admin management panel (staff only)"),
    BotCommand("settings", "Configure the request bot"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(LELOUCH_COMMANDS)


def build_lelouch(container: Container, token: str) -> Client:
    """Build and wire the Lelouch (Request) bot client.

    Reuses NekoFetch's existing handlers via ``register_all`` — the same
    AniList search, franchise confirmation, and TMDB enrichment logic
    that the admin bot already uses, with Lelouch-specific dedup and
    admin assignment layered on top.
    """
    client = Client(
        name="kage-lelouch",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    # ── Register all handlers (middleware + request flow) ─────────────────────
    from kage.bots.lelouch.handlers import register_all

    register_all(client, container)

    # ── Catch-all menu callback ─────────────────────────────────────────────
    # Inline buttons on /start route to `lelouch|<action>`. Real handlers
    # match `req|`, `ver_pick`, `series_yes/no`, `noop`. Whatever falls through
    # gets a one-line alert so the user isn't left with a silent dead button.
    from pyrogram.types import CallbackQuery

    @client.on_callback_query(filters.regex(r"^lelouch\|"))
    async def _lelouch_menu_fallback(_: Client, q: CallbackQuery) -> None:
        try:
            _, action = q.data.split("|", 1)
        except ValueError:
            action = "help"
        await q.answer(f"Type /{action} in chat.", show_alert=False)

    # ── /start ────────────────────────────────────────────────────────────────
    # Rich UI: sticker → loading animation → welcome screen with inline keyboard
    # and Lelouch-themed artwork (images/lelouch/).
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.domain.enums import Role
        from nekofetch.ui.screens import welcome as welcome_screen
        from kage.shared.ui_helpers import send_rich_welcome

        user = getattr(message, "nf_user", None)
        role = Role(user.role) if user else Role.USER
        name = message.from_user.first_name if message.from_user else ""

        # welcome_screen() builds a NekoFetch-parity screen with the
        # Request Anime / My Requests inline buttons + staff/admin extras;
        # passing bot_name="lelouch" picks artwork from images/lelouch/.
        screen = welcome_screen(
            name,
            is_staff=role in (Role.STAFF, Role.ADMIN),
            is_admin=role is Role.ADMIN,
            bot_name="lelouch",
        )
        await send_rich_welcome(client, container, message, screen, bot_name="lelouch")

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        await message.reply(
            "<b>🎭 Lelouch Vi Britannia — Request Bot</b>\n\n"
            "<b>How to request:</b>\n"
            "1. Send me any anime title.\n"
            "2. I'll check if it already exists.\n"
            "3. If new, I'll search AniList and confirm the franchise.\n"
            "4. Once confirmed, I assign it to our download team.\n\n"
            "<b>Rules:</b>\n"
            "• One active request at a time (staff can batch).\n"
            "• You'll be notified when your anime is published.\n\n"
            "<b>Commands:</b>\n"
            "/start — New request\n"
            "/myrequests — Your requests\n"
            "/help — This help",
            parse_mode=ParseMode.HTML,
        )

    # ── /myrequests ───────────────────────────────────────────────────────────
    @client.on_message(filters.command("myrequests"))
    async def _myrequests(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        from nekofetch.services.request_service import RequestService

        rows = await RequestService(container).list_for_user(message.from_user.id)
        if not rows:
            await message.reply(
                "📭 <b>No requests yet!</b>\n\n"
                "Send me an anime title to get started.",
                parse_mode=ParseMode.HTML,
            )
            return

        lines = ["<b>📋 Your Requests</b>\n"]
        for r in rows[:10]:
            status_val = r.status.value if hasattr(r.status, 'value') else str(r.status)
            status_emoji = {
                "pending": "⏳", "approved": "✅", "queued": "📥",
                "downloading": "⬇️", "processing": "⚙️", "ready": "📦",
                "published": "🎉", "rejected": "❌", "failed": "⚠️",
            }.get(status_val, "❓")
            lines.append(
                f"{status_emoji} <b>{r.anime_title}</b> — "
                f"<code>{r.code}</code> ({status_val})"
            )

        await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── /admin ────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("admin"))
    async def _admin(_: Client, message: Message) -> None:
        from nekofetch.domain.enums import Role

        user = getattr(message, "nf_user", None)
        role = Role(user.role) if user else Role.USER
        if role not in (Role.STAFF, Role.ADMIN):
            await message.reply("🔒 <b>Staff only.</b>", parse_mode=ParseMode.HTML)
            return

        from nekofetch.ui.components import cb, keyboard
        from nekofetch.ui.screens import Screen, send_screen

        rows = [
            [("📋 Pending Requests", cb("lelouch", "pending")),
             ("👥 Manage Admins", cb("lelouch", "manage"))],
            [("📊 Availability", cb("lelouch", "avail")),
             ("⚙️ Settings", cb("lelouch", "settings"))],
        ]
        screen = Screen(
            caption="<b>🎭 Lelouch Vi Britannia — Admin Panel</b>\n\n"
                     "Manage requests, admins, and availability.",
            keyboard=keyboard(*rows),
        )
        await send_screen(client, message.chat.id, screen)

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen
        from nekofetch.ui.components import cb, keyboard

        screen = Screen(
            caption="<b>⚙️ Lelouch Settings</b>\n\n"
                     "Configure request limits, admin pools, and availability.",
            keyboard=keyboard(
                [("Request Limits", cb("lelouch", "set", "limits")),
                 ("Admin Pool", cb("lelouch", "set", "admins"))],
                [("Back", cb("lelouch", "home"))],
            ),
        )
        await send_screen(client, message.chat.id, screen)

    return client
