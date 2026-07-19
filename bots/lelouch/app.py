"""Lelouch vi Britannia — Request Bot (影の司令官 · The Shadow Commander).

Handles:
  • User request intake — reuses NekoFetch's AniList search + franchise flow.
  • Duplicate detection before accepting (main channel → distribution → in-progress).
  • One-request-at-a-time limit for regular users.
  • Admin batch work support (marshalled into the work-item queue).
  • Admin assignment to the downloader stage.
  • Management (availability, breaks, working hours, reassignment).
  • Per-bot settings panel.

Routing contract (the fix for "buttons do nothing"): every Lelouch screen is
built by :mod:`kurosoden.bots.lelouch.screens` and emits callbacks in exactly
three namespaces — ``lelouch|…`` (this dispatcher), ``req|…`` (the request
handler), and ``batch|…`` (the reused NekoFetch batch handler). We also install
bridges for the generic ``welcome()`` screen's ``home`` / ``admin|home`` /
``queue|view`` callbacks so no button is ever a dead tap.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, CallbackQuery, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

LELOUCH_COMMANDS = [
    BotCommand("start", "Submit a new anime request"),
    BotCommand("myrequests", "View your request status"),
    BotCommand("help", "How requests work"),
    BotCommand("admin", "Command panel (staff only)"),
    BotCommand("settings", "Configure the request bot"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(LELOUCH_COMMANDS)


def build_lelouch(container: Container, token: str) -> Client:
    """Build and wire the Lelouch (Request) bot client."""
    client = Client(
        name="kurosoden-lelouch",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    # ── Register request-flow handlers (middleware + intake + batch) ──────────
    from kurosoden.bots.lelouch.handlers import register_all

    register_all(client, container)

    # ── Shared imports for the dispatcher ─────────────────────────────────────
    from nekofetch.domain.enums import Role
    from nekofetch.ui.screens import send_screen
    from kurosoden.bots.lelouch import screens as S
    from kurosoden.shared import lelouch_voice as V
    from kurosoden.shared.request_gate import (
        get_mode,
        requests_open,
        set_requests_open,
    )
    from kurosoden.shared.work_service import WorkService

    # ── Small role/state helpers ──────────────────────────────────────────────
    def _role(obj) -> Role:
        user = getattr(obj, "nf_user", None)
        return Role(user.role) if user else Role.USER

    def _first_name(obj) -> str:
        u = getattr(obj, "from_user", None)
        return (u.first_name if u else "") or ""

    async def _counts() -> tuple[int, int]:
        """(pending requests, open work items) — best effort, never raises."""
        pending = 0
        try:
            pending = len(await _request_service().list_pending())
        except Exception:  # noqa: BLE001 — a count is decorative, never fatal
            pass
        work_open = 0
        try:
            work_open = await WorkService(container.pg_sessionmaker).count_open()
        except Exception:  # noqa: BLE001
            pass
        return pending, work_open

    def _request_service():
        from nekofetch.services.request_service import RequestService
        return RequestService(container)

    async def _render_home(chat_id: int, obj, old_msg: Message | None = None) -> None:
        role = _role(obj)
        screen = S.home(
            _first_name(obj),
            is_staff=role in (Role.STAFF, Role.ADMIN),
            is_admin=role is Role.ADMIN,
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    async def _render_admin(chat_id: int, old_msg: Message | None = None) -> None:
        is_open = await requests_open(container)
        mode = await get_mode(container)
        pending, work_open = await _counts()
        screen = S.admin_panel(mode=mode, requests_open=is_open,
                               pending=pending, work_open=work_open)
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    # ── Main menu dispatcher — every lelouch|<action> resolves here ───────────
    @client.on_callback_query(filters.regex(r"^lelouch\|"))
    async def _menu(_: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        parts = q.data.split("|", 2)
        action = parts[1] if len(parts) > 1 else "home"
        arg = parts[2] if len(parts) > 2 else ""
        chat_id = q.message.chat.id
        staff = _role(q) in (Role.STAFF, Role.ADMIN)

        # ¬¬ Home ¬¬
        if action == "home":
            await _render_home(chat_id, q, old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Settings ¬¬ — the shared human-friendly engine owns lelouch|settings
        # and lelouch|set|… (registered first in register_all, so it wins here).

        # ── Everything below is staff-only ──
        if not staff:
            await q.answer("🔒 Command is staff only.", show_alert=True)
            return

        if action == "admin":
            await _render_admin(chat_id, old_msg=q.message)
            await q.answer()
            return

        if action == "reqtoggle":
            new_state = not await requests_open(container)
            await set_requests_open(container, new_state)
            await q.answer("🟢 Requests resumed." if new_state
                           else "🔴 Requests paused.")
            await _render_admin(chat_id, old_msg=q.message)
            return

        if action == "queue":
            pending, work_open = await _counts()
            await send_screen(client, chat_id,
                              S.queue(pending=pending, work_open=work_open,
                                      back="admin"),
                              old_msg=q.message)
            await q.answer()
            return

        if action == "manage":
            from kurosoden.bots.lelouch.handlers.management import render_manage
            await render_manage(client, container, chat_id, q.message)
            await q.answer()
            return

        if action == "avail":
            from kurosoden.bots.lelouch.handlers.management import render_availability
            await render_availability(client, container, chat_id, q.message)
            await q.answer()
            return

        if action == "hours":
            from kurosoden.bots.lelouch.handlers.management import render_hours
            await render_hours(client, container, chat_id, q.message)
            await q.answer()
            return

        if action == "pending":
            # Hand off to the reused NekoFetch staff review list, which owns the
            # rich per-request detail flow. Its own callbacks (staff|…) are
            # registered on this client by register_all → review.register.
            from nekofetch.ui.components import cb
            from nekofetch.ui.screens import card
            pending, _work = await _counts()
            screen = card(
                f"{V.ICON} <b>Pending Requests</b>\n\n"
                f"<b>{pending}</b> awaiting a source. Open the review board to "
                f"assign and act on each one.\n\n"
                "<i>Indecision is the only true defeat. Move.</i>",
                bot_name="lelouch",
                buttons=[[("📋 Open Review Board", cb("staff", "requests", 0))],
                         [(V.BTN_BACK_ADMIN, cb("lelouch", "admin"))]],
            )
            await send_screen(client, chat_id, screen, old_msg=q.message)
            await q.answer()
            return

        await q.answer(V.UNKNOWN_ACTION, show_alert=True)

    # ── Bridges for the generic welcome() screen's callbacks ──────────────────
    # If any surface still ships NekoFetch's stock welcome (bare `home`,
    # `admin|home`, `queue|view|<page>`), route it home/admin instead of a dead
    # tap. Grouped after the main dispatcher so lelouch|… wins first.
    @client.on_callback_query(filters.regex(r"^home$"))
    async def _bridge_home(_: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        await _render_home(q.message.chat.id, q, old_msg=q.message)
        await q.answer()

    @client.on_callback_query(filters.regex(r"^admin\|home$"))
    async def _bridge_admin(_: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        if _role(q) not in (Role.STAFF, Role.ADMIN):
            await q.answer("🔒 Command is staff only.", show_alert=True)
            return
        await _render_admin(q.message.chat.id, old_msg=q.message)
        await q.answer()

    @client.on_callback_query(filters.regex(r"^queue\|view"))
    async def _bridge_queue(_: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        if _role(q) not in (Role.STAFF, Role.ADMIN):
            await q.answer("🔒 Command is staff only.", show_alert=True)
            return
        pending, work_open = await _counts()
        await send_screen(client, q.message.chat.id,
                          S.queue(pending=pending, work_open=work_open,
                                  back="home"),
                          old_msg=q.message)
        await q.answer()

    # ── /start — theatrical welcome, our own Lelouch home card ────────────────
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from kurosoden.shared.ui_helpers import send_rich_welcome

        role = _role(message)
        screen = S.home(
            _first_name(message),
            is_staff=role in (Role.STAFF, Role.ADMIN),
            is_admin=role is Role.ADMIN,
        )
        await send_rich_welcome(client, container, message, screen, bot_name="lelouch")

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        from nekofetch.ui.components import cb
        from nekofetch.ui.screens import card

        caption = (
            f"{V.ICON} <b>How the game is played</b>\n\n"
            "1. Send me any anime title.\n"
            "2. I confirm it doesn't already exist in our arsenal.\n"
            "3. If it's new, I hunt down its true form and confirm the franchise.\n"
            "4. Once you approve, I hand it to the ones who bring it home.\n\n"
            "<b>The rules:</b>\n"
            "• One request in play at a time — staff may batch work.\n"
            "• You'll be told the moment your anime is published.\n\n"
            "<i>Make your move.</i>"
        )
        await send_screen(
            client, message.chat.id,
            card(caption, bot_name="lelouch",
                 buttons=[[(V.BTN_HOME, cb("lelouch", "home"))]]),
        )

    # ── /myrequests ───────────────────────────────────────────────────────────
    @client.on_message(filters.command("myrequests"))
    async def _myrequests(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        from nekofetch.ui.components import cb
        from nekofetch.ui.screens import card

        rows = await _request_service().list_for_user(message.from_user.id)
        if not rows:
            caption = (
                f"{V.ICON} <b>Your board is empty.</b>\n\n"
                "You hold no requests yet. Name an anime and I'll set the machine "
                "in motion.\n\n"
                "<i>Every campaign begins with a single move.</i>"
            )
            await send_screen(
                client, message.chat.id,
                card(caption, bot_name="lelouch",
                     buttons=[[(V.BTN_REQUEST, cb("req", "new"))],
                              [(V.BTN_HOME, cb("lelouch", "home"))]]),
            )
            return

        emoji = {
            "pending": "⏳", "approved": "✅", "queued": "📥",
            "downloading": "⬇️", "processing": "⚙️", "ready": "📦",
            "published": "🎉", "rejected": "❌", "failed": "⚠️",
        }
        lines = [f"{V.ICON} <b>Your Requests</b>", ""]
        for r in rows[:10]:
            status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
            lines.append(
                f"{emoji.get(status_val, '❓')} <b>{V.esc(r.anime_title)}</b> — "
                f"<code>{V.esc(r.code)}</code> ({V.esc(status_val)})"
            )
        await send_screen(
            client, message.chat.id,
            card("\n".join(lines), bot_name="lelouch",
                 buttons=[[(V.BTN_REQUEST, cb("req", "new"))],
                          [(V.BTN_HOME, cb("lelouch", "home"))]]),
        )

    # ── /admin ────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("admin"))
    async def _admin(_: Client, message: Message) -> None:
        if _role(message) not in (Role.STAFF, Role.ADMIN):
            await message.reply("🔒 <b>Command is staff only.</b>",
                                parse_mode=ParseMode.HTML)
            return
        await _render_admin(message.chat.id)

    # ── /settings ── owned by the shared human-friendly settings engine
    # (register_settings in handlers/__init__.py), under lelouch|set|….

    return client
