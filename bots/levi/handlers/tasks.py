"""Levi task handlers — the downloader's task list.

Levi does NOT reimplement the download flow. The real machinery — source pick,
website coverage report, seeders-ranked torrent picker, franchise-entry mapping,
and queueing — lives in NekoFetch's admin ``review`` handler, which
``register_all`` mounts onto this same client. This module owns the visible task
cards and drops confirmed source choices into that shared machinery.

So the flow the user sees is:

    Open a task  →  Levi-native request card
                 →  Pick source (Website / Torrent / Telegram-manual)
                 →  Read the source report / seeders list
                 →  Pick which franchise entries to pull
                 →  It queues; the background worker downloads + processes.
"""

from __future__ import annotations

import html

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from kurosoden.shared import levi_voice as V
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.ui.artwork import (
    ensure_anime_art,
    key_for_franchise,
    next_anime_art,
    pick_artwork,
)
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import Screen, send_screen

log = get_logger(__name__)
LEVI_COMMANDS = ["start", "help", "tasks", "settings"]


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _requester_label(req) -> str:
    user = getattr(req, "user", None)
    if user is None:
        return "unknown"
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or "user"
    telegram_id = getattr(user, "telegram_id", None)
    return f"{name} ({telegram_id})" if telegram_id is not None else name


def _franchise_line(franchise: dict | None) -> str:
    fr = franchise or {}
    bits = []
    for key, label in (
        ("franchise_seasons", "season"),
        ("franchise_movies", "movie"),
        ("franchise_ovas", "OVA"),
        ("franchise_onas", "ONA"),
        ("franchise_specials", "special"),
    ):
        count = int(fr.get(key) or 0)
        if count:
            suffix = "" if count == 1 or label in {"OVA", "ONA"} else "s"
            bits.append(f"{count} {label}{suffix}")
    episodes = int(fr.get("franchise_episodes") or 0)
    if episodes:
        bits.append(f"{episodes} eps")
    return " · ".join(bits) if bits else "single entry"


def _request_card(req, *, offered: bool = False) -> str:
    title = (req.franchise_data or {}).get("title") or req.anime_title
    header = "Optional download detail" if offered else "Download detail assigned"
    body = (
        "Quiet-hour offer. Accept it if you're taking the cut now; reject it and the "
        "ladder moves without marking the request dead."
        if offered else
        "Pick the source from this card. Report first if you want the terrain; source "
        "selection drops straight into the downloader."
    )
    return (
        f"{V.ICON} <b>{header}</b>\n\n"
        f"<blockquote><b>{_esc(title)}</b>\n"
        f"<code>{_esc(req.code)}</code>\n"
        f"<b>Requester:</b> {_esc(_requester_label(req))}\n"
        f"<b>Contents:</b> {_esc(_franchise_line(req.franchise_data))}\n"
        f"<b>Status:</b> {_esc(getattr(req.status, 'value', req.status))}</blockquote>\n\n"
        f"<i>{body}</i>"
    )


def register(client: Client, container: Container) -> None:
    """Register Levi's task list — the entry point into the shared download flow."""

    async def _render_tasks(chat_id: int, admin_id: int,
                            old_msg: Message | None = None) -> None:
        """Build and send the assigned-tasks screen with one Open button per task."""
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.repositories.request_repo import RequestRepository

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        active = await engine.get_active_tasks(admin_id)
        offers = await engine.get_pending_offers(admin_id)

        if not active and not offers:
            screen = Screen(
                caption=(
                    "<b>⚔️ No download tasks right now.</b>\n\n"
                    "When a request is routed to you, it shows up here — tap it to "
                    "pick a source and start the download."
                ),
                image=pick_artwork("levi"),
                keyboard=keyboard([("⇐ Back", cb("levi", "home"))]),
            )
            await send_screen(client, chat_id, screen, old_msg=old_msg)
            return

        # Resolve titles in one session pass so the list reads like anime, not codes.
        titles: dict[str, str] = {}
        try:
            async with session_scope(container.pg_sessionmaker) as s:
                repo = RequestRepository(s)
                for a in [*offers[:5], *active[:10]]:
                    req = await repo.get_by_code(a.request_code)
                    titles[a.request_code] = req.anime_title if req else a.request_code
        except Exception:  # noqa: BLE001 - fall back to codes; never blank the list
            pass

        lines = ["<b>⚔️ Your Download Tasks</b>", ""]
        rows: list[tuple[str, str]] = []
        if offers:
            lines.append("<b>Pending offers</b>")
            for a in offers[:5]:
                title = titles.get(a.request_code, a.request_code)
                lines.append(f"Offer  <b>{title}</b>  <code>{a.request_code}</code>")
                rows.append((f"⚔️ Review offer · {title[:26]}",
                             cb("levi", "task", a.request_code)))
            lines.append("")
        if active:
            lines.append("<b>Assigned</b>")
        for a in active[:10]:
            icon = "🔄" if a.status == "in_progress" else "⏳"
            title = titles.get(a.request_code, a.request_code)
            lines.append(f"{icon}  <b>{title}</b>  ·  <code>{a.request_code}</code>")
            rows.append((f"▶️ Open · {title[:28]}",
                         cb("levi", "task", a.request_code)))

        lines += ["", "<i>Tap a task to pick a source and begin.</i>"]
        # One Open button per row, then a Back control.
        kb_rows = [[r] for r in rows]
        kb_rows.append([("⇐ Back", cb("levi", "home"))])
        screen = Screen(
            caption="\n".join(lines),
            image=pick_artwork("levi"),
            keyboard=keyboard(*kb_rows),
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    async def _load_request(code: str):
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.repositories.request_repo import RequestRepository

        async with session_scope(container.pg_sessionmaker) as session:
            return await RequestRepository(session).get_by_code(code)

    async def _has_pending_offer(admin_id: int, code: str) -> bool:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        offers = await engine.get_pending_offers(admin_id)
        return any(a.request_code == code for a in offers)

    async def _anime_image(req) -> object:
        franchise = req.franchise_data or {}
        title = franchise.get("title") or req.anime_title
        art_key = key_for_franchise(franchise, title=title)
        await ensure_anime_art(art_key, franchise=franchise)
        return next_anime_art(art_key, fallback_bot="levi")

    async def _render_detail(
        chat_id: int,
        code: str,
        old_msg: Message | None = None,
        *,
        offered: bool = False,
    ) -> None:
        req = await _load_request(code)
        if req is None:
            screen = Screen(
                caption=f"{V.ICON} <b>Request not found.</b>\n\n<code>{_esc(code)}</code>",
                image=pick_artwork("levi"),
                keyboard=keyboard([("⇐ Back", cb("levi", "tasks"))]),
            )
            await send_screen(client, chat_id, screen, old_msg=old_msg)
            return

        if offered:
            kb = keyboard(
                [("Accept", cb("levi", "offer", "accept", code)),
                 ("Reject", cb("levi", "offer", "reject", code))],
                [("⇐ Tasks", cb("levi", "tasks"))],
            )
        else:
            kb = keyboard(
                [(V.BTN_REPORT, cb("staff", "rsource", code, "website"))],
                [(V.BTN_SRC_TELEGRAM, cb("staff", "rsource", code, "telegram"))],
                [(V.BTN_SRC_TORRENT, cb("staff", "rsource", code, "torrent"))],
                [("I can't take this", cb("levi", "decline", code))],
                [("⇐ Tasks", cb("levi", "tasks"))],
            )
        screen = Screen(
            caption=_request_card(req, offered=offered),
            image=await _anime_image(req),
            keyboard=kb,
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    # ── /tasks — the assigned-task list ────────────────────────────────────
    @client.on_message(filters.command("tasks"))
    async def _tasks_cmd(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        await _render_tasks(message.chat.id, message.from_user.id)

    # ── levi|tasks — same list, from the inline menu ───────────────────────
    @client.on_callback_query(filters.regex(r"^levi\|tasks$"))
    async def _tasks_cb(_: Client, q: CallbackQuery) -> None:
        if q.message is None or q.from_user is None:
            await q.answer()
            return
        await q.answer()
        await _render_tasks(q.message.chat.id, q.from_user.id, old_msg=q.message)

    @client.on_callback_query(filters.regex(r"^levi\|task\|"))
    async def _task_cb(_: Client, q: CallbackQuery) -> None:
        if q.message is None or q.from_user is None:
            await q.answer()
            return
        code = (q.data or "").split("|", 2)[2]
        offered = await _has_pending_offer(q.from_user.id, code)
        await q.answer()
        await _render_detail(q.message.chat.id, code, old_msg=q.message, offered=offered)

    @client.on_callback_query(filters.regex(r"^levi\|offer\|"))
    async def _offer_cb(_: Client, q: CallbackQuery) -> None:
        if q.message is None or q.from_user is None:
            await q.answer()
            return
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        parts = (q.data or "").split("|", 3)
        action = parts[2] if len(parts) > 2 else ""
        code = parts[3] if len(parts) > 3 else ""
        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        if action == "accept":
            result = await engine.accept_offer(code, "levi", q.from_user.id)
            await q.answer("Accepted." if result else "Offer expired.", show_alert=result is None)
            if result:
                await _render_detail(q.message.chat.id, code, old_msg=q.message)
                return
        elif action == "reject":
            ok = await engine.reject_offer(code, "levi", q.from_user.id)
            await q.answer("Rejected." if ok else "Offer expired.", show_alert=not ok)
        else:
            await q.answer()
        await _render_tasks(q.message.chat.id, q.from_user.id, old_msg=q.message)

    @client.on_callback_query(filters.regex(r"^levi\|decline\|"))
    async def _decline_cb(_: Client, q: CallbackQuery) -> None:
        if q.message is None or q.from_user is None:
            await q.answer()
            return
        code = (q.data or "").split("|", 2)[2]
        if container.redis:
            await container.redis.set(f"nf:levi:decline:{q.from_user.id}", code, ex=1800)
        kb = keyboard(
            [("⇐ Back to request", cb("levi", "task", code))],
            [("⇐ Tasks", cb("levi", "tasks"))],
        )
        await q.answer()
        await send_screen(
            client,
            q.message.chat.id,
            Screen(
                caption=(
                    f"{V.ICON} <b>Reason required.</b>\n\n"
                    f"<code>{_esc(code)}</code>\n"
                    "Send the reason in one message. The owner gets it through Lelouch; "
                    "the request stays alive until the owner cancels or reassigns it."
                ),
                image=pick_artwork("levi"),
                keyboard=kb,
            ),
            old_msg=q.message,
        )

    @client.on_message(filters.text & ~filters.command(LEVI_COMMANDS))
    async def _decline_reason(_: Client, message: Message) -> None:
        if message.from_user is None or container.redis is None:
            return
        key = f"nf:levi:decline:{message.from_user.id}"
        code = await container.redis.get(key)
        if not code:
            return
        if isinstance(code, bytes):
            code = code.decode()
        await container.redis.delete(key)
        reason = (message.text or "").strip()
        if not reason:
            return
        req = await _load_request(code)
        title = (req.franchise_data or {}).get("title") if req else None
        title = title or (req.anime_title if req else code)
        owner_id = None
        try:
            from kurosoden.shared.owner_seed import _owner_id

            owner_id = _owner_id(container)
        except Exception:  # noqa: BLE001
            owner_id = None
        notifier = getattr(getattr(container, "pipeline_manager", None), "lelouch", None)
        if owner_id and notifier is not None:
            admin_name = _esc(
                message.from_user.first_name or message.from_user.username or "user"
            )
            await notifier.send_message(
                int(owner_id),
                (
                    "♟️ <b>Levi decline request</b>\n\n"
                    f"<b>Anime:</b> {_esc(title)}\n"
                    f"<b>Request:</b> <code>{_esc(code)}</code>\n"
                    f"<b>Admin:</b> {admin_name} (<code>{message.from_user.id}</code>)\n\n"
                    f"<blockquote>{_esc(reason)}</blockquote>\n\n"
                    "Decide whether to cancel the series or reassign it."
                ),
                parse_mode=ParseMode.HTML,
            )
        await message.reply_text(
            f"{V.ICON} <b>Sent to owner.</b>\n\nThe request is still alive.",
            parse_mode=ParseMode.HTML,
        )
