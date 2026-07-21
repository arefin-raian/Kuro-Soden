"""Levi task handlers — the downloader's task list.

Levi does NOT reimplement the download flow. The real machinery — source pick,
website coverage report, seeders-ranked torrent picker, franchise-entry mapping,
and queueing — lives in NekoFetch's admin ``review`` handler, which
``register_all`` mounts onto this same client. This module only lists the tasks
assigned to the admin and hands each one to that flow via ``staff|rdetail|<code>``.

So the flow the user sees is:

    Open a task  →  Pick source (Website / Torrent / Telegram-manual)
                 →  Read the source report / seeders list
                 →  Pick which franchise entries to pull
                 →  It queues; the background worker downloads + processes.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import Screen, send_screen

log = get_logger(__name__)


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
                rows.append((f"Accept - {title[:26]}",
                             cb("levi", "offer", "accept", a.request_code)))
                rows.append((f"Reject - {title[:26]}",
                             cb("levi", "offer", "reject", a.request_code)))
            lines.append("")
        if active:
            lines.append("<b>Assigned</b>")
        for a in active[:10]:
            icon = "🔄" if a.status == "in_progress" else "⏳"
            title = titles.get(a.request_code, a.request_code)
            lines.append(f"{icon}  <b>{title}</b>  ·  <code>{a.request_code}</code>")
            rows.append((f"▶️ Open · {title[:28]}",
                         cb("staff", "rdetail", a.request_code)))

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
        elif action == "reject":
            ok = await engine.reject_offer(code, "levi", q.from_user.id)
            await q.answer("Rejected." if ok else "Offer expired.", show_alert=not ok)
        else:
            await q.answer()
        await _render_tasks(q.message.chat.id, q.from_user.id, old_msg=q.message)
