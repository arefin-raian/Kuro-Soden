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
from kage.shared.ui_helpers import reply_with_screen
from nekofetch.ui.artwork import pick_artwork

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
    # Inline buttons on /start route to `lelouch|<action>`. The dispatcher below
    # maps every action to a real screen — no more "Type /X in chat" toasts.
    from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                                InlineKeyboardMarkup)
    from kage.shared.menu_router import settings_hub, settings_onboarding, tool_screen
    from kage.shared.settings_content import ALL_BY_BOT
    from nekofetch.ui.components import cb
    from nekofetch.ui.screens import Screen, send_screen
    from nekofetch.domain.enums import Role

    @client.on_callback_query(filters.regex(r"^lelouch\|"))
    async def _lelouch_menu_fallback(client: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        parts = q.data.split("|", 2)
        action = parts[1] if len(parts) > 1 else "home"
        arg = parts[2] if len(parts) > 2 else ""
        bot = "lelouch"

        # ¬¬ Home ¬¬
        if action == "home":
            caption = (
                "<b>🎭 Lelouch — Request Bot</b>\n\n"
                "<i>\"The only ones who should kill are those prepared to die.\"</i>\n\n"
                "I handle the intake pipeline:\n"
                "â€¢ Search AniList / TMDB\n"
                "â€¢ Franchise confirmation\n"
                "â€¢ Dedup across main / dist / in-progress\n"
                "â€¢ Auto-assign to downloader admins"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Request Anime", callback_data=cb("req", "new")),
                 InlineKeyboardButton("📥 My Requests", callback_data=cb("req", "mine", 0))],
                [InlineKeyboardButton("⚙️ Settings", callback_data=cb(bot, "settings")),
                 InlineKeyboardButton("🛡 Admin Panel", callback_data=cb(bot, "admin"))],
            ])
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Admin ¬¬
        if action == "admin":
            user = getattr(q, "nf_user", None)
            role = Role(user.role) if user else Role.USER
            if role not in (Role.STAFF, Role.ADMIN):
                await q.answer("🔒 Staff only.", show_alert=True)
                return
            caption = (
                "<b>🎭 Lelouch — Admin Panel</b>\n\n"
                "<i>Manage requests, admins, and availability.</i>\n\n"
                "<blockquote>Staff-only tools. Non-staff tap = access denied toast.</blockquote>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Pending Requests", callback_data=cb(bot, "pending")),
                 InlineKeyboardButton("👥 Manage Admins", callback_data=cb(bot, "manage"))],
                [InlineKeyboardButton("📊 Availability", callback_data=cb(bot, "avail")),
                 InlineKeyboardButton("⚙️ Settings", callback_data=cb(bot, "settings"))],
                [InlineKeyboardButton("⇐ Back to Home", callback_data=cb(bot, "home"))],
            ])
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Settings hub ¬¬
        if action == "settings":
            caption, keyboard = settings_hub(
                bot, title="Lelouch Settings",
                body=("Configure request limits, admin pools, and availability.\n\n"
                      "<i>Tap a row to open the help panel for that key, then "
                      "send the new value as a chat message.</i>"),
                items=[("Request Limits", "limits"), ("Admin Pool", "admins")],
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

        # ¬¬ Admin placeholder actions (staff actions land next round) ¬¬
        if action in ("pending", "manage", "avail"):
            tmap = {"pending": "Pending Requests",
                    "manage": "Manage Admins",
                    "avail": "Availability"}
            caption, _ = tool_screen(
                bot, title=tmap[action],
                kicker="Tap from the panel — full controls land next round.",
                lines=[f"<b>Coming up:</b> {action} controls."],
                back="admin",
                back_label="⇐ Back to Admin",
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=InlineKeyboardMarkup([[
                                         InlineKeyboardButton(
                                             "⇐ Back to Admin",
                                             callback_data=cb(bot, "admin"),
                                         ),
                                     ]])), old_msg=q.message)
            await q.answer()
            return

        await q.answer(f"Action “{action}” not wired yet.", show_alert=True)

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
        await send_rich_welcome(client, container, message, screen)

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        caption = (
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
            "/help — This help"
        )
        await reply_with_screen(
            client, message.chat.id, caption, bot_name="lelouch",
        )

    # ── /myrequests ───────────────────────────────────────────────────────────
    @client.on_message(filters.command("myrequests"))
    async def _myrequests(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        from nekofetch.services.request_service import RequestService

        rows = await RequestService(container).list_for_user(message.from_user.id)
        if not rows:
            await reply_with_screen(
                client, message.chat.id,
                "📭 <b>No requests yet!</b>\n\n"
                "Send me an anime title to get started.",
                bot_name="lelouch",
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

        await reply_with_screen(
            client, message.chat.id, "\n".join(lines), bot_name="lelouch",
        )

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
            image=pick_artwork("lelouch"),
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
            image=pick_artwork("lelouch"),
        )
        await send_screen(client, message.chat.id, screen)

    return client
