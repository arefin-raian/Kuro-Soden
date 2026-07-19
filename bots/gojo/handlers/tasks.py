"""Gojo task handlers — REUSES NekoFetch's publishing infrastructure.

Key principle: Gojo does NOT reimplement publishing. It delegates to:
  • MainChannelService.publish() — generates and posts to the main channel.
  • IndexChannelService.refresh_letter() — updates the A-Z index.
  • PublishingService.publish() — the full publish orchestration.
  • BotOrchestratorService — recreates bots for channel recovery.
"""

from __future__ import annotations

from datetime import datetime

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.screens import Screen, send_screen
from kurosoden.shared import gojo_voice as V

log = get_logger(__name__)

STATE_EDIT_CAPTION = "gojo:await_caption_edit"
STATE_SCHEDULE = "gojo:await_schedule"
STATE_EDIT_FOOTER = "gojo:await_footer_edit"


def _publish_keyboard(code: str):
    """The review card's action row — publish now / silent / schedule / edit."""
    return keyboard(
        [(V.BTN_PUBLISH_NOW, cb("gojo", "publish_confirm", code)),
         (V.BTN_PUBLISH_SILENT, cb("gojo", "publish_silent", code))],
        [(V.BTN_SCHEDULE, cb("gojo", "publish_schedule", code)),
         (V.BTN_EDIT_CAPTION, cb("gojo", "publish_edit", code))],
        [(V.BTN_CANCEL, cb("gojo", "home"))],
    )


def register(client: Client, container: Container) -> None:
    fsm = FSM(container.redis, bot="gojo")

    # ── /tasks — View assigned publishing tasks ───────────────────────────────
    @client.on_message(filters.command("tasks"))
    async def _tasks(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.repositories.request_repo import RequestRepository

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        active = await engine.get_active_tasks(message.from_user.id)

        if not active:
            await message.reply(
                "<b>🔮 No active publishing tasks.</b>\n\n"
                "No anime assigned to you for publishing right now.",
                parse_mode=ParseMode.HTML,
            )
            return

        lines = ["<b>🔮 Your Publishing Tasks</b>\n"]
        for a in active[:10]:
            status_icon = "🔄" if a.status == "in_progress" else "⏳"
            title = a.request_code
            try:
                async with session_scope(container.pg_sessionmaker) as s:
                    req = await RequestRepository(s).get_by_code(a.request_code)
                    if req:
                        title = req.anime_title
            except Exception:
                pass
            lines.append(f"{status_icon} <code>{a.request_code}</code> — <b>{title}</b>")
        await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── Callback handlers (registered ONCE, not dynamically) ────────────────
    @client.on_callback_query(filters.regex(r"^gojo\|publish_confirm\|"))
    async def _cb_publish(_: Client, q: CallbackQuery) -> None:
        _, _, code = q.data.split("|", 2)
        await q.answer("Publishing...")
        await _execute_publish(client, container, q.message, code, silent=False)

    @client.on_callback_query(filters.regex(r"^gojo\|publish_silent\|"))
    async def _cb_publish_silent(_: Client, q: CallbackQuery) -> None:
        _, _, code = q.data.split("|", 2)
        await q.answer("Publishing silently...")
        await _execute_publish(client, container, q.message, code, silent=True)

    @client.on_callback_query(filters.regex(r"^gojo\|publish_edit\|"))
    async def _cb_edit(_: Client, q: CallbackQuery) -> None:
        _, _, code = q.data.split("|", 2)
        await q.answer()
        await fsm.set(q.from_user.id, STATE_EDIT_CAPTION, request_code=code)
        await q.message.reply(V.EDIT_CAPTION_PROMPT, parse_mode=ParseMode.HTML)

    @client.on_callback_query(filters.regex(r"^gojo\|publish_schedule\|"))
    async def _cb_schedule(_: Client, q: CallbackQuery) -> None:
        _, _, code = q.data.split("|", 2)
        await q.answer()
        await fsm.set(q.from_user.id, STATE_SCHEDULE, request_code=code)
        await q.message.reply(V.SCHEDULE_PROMPT, parse_mode=ParseMode.HTML)

    # ── Universal footer edit — /footer or the gojo|edit_footer button ────────
    async def _arm_footer(user_id: int, reply_to: Message) -> None:
        await fsm.set(user_id, STATE_EDIT_FOOTER)
        await reply_to.reply(V.FOOTER_EDIT_PROMPT, parse_mode=ParseMode.HTML)

    @client.on_message(filters.command("footer"))
    async def _footer_cmd(_: Client, message: Message) -> None:
        if message.from_user:
            await _arm_footer(message.from_user.id, message)

    @client.on_callback_query(filters.regex(r"^gojo\|edit_footer$"))
    async def _cb_footer(_: Client, q: CallbackQuery) -> None:
        await q.answer()
        await _arm_footer(q.from_user.id, q.message)

    # ── FSM text consumer — caption edit + schedule time ──────────────────────
    @client.on_message(filters.text & filters.private & ~filters.command(["cancel"]))
    async def _fsm_text(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, data = await fsm.get(message.from_user.id)
        code = data.get("request_code")
        if state == STATE_EDIT_CAPTION and code:
            from kurosoden.shared.settings_ui import parse_user_markup

            caption = parse_user_markup(message)
            await fsm.clear(message.from_user.id)
            await _execute_publish(
                client, container, message, code,
                silent=False, caption_override=caption,
            )
        elif state == STATE_SCHEDULE and code:
            raw = (message.text or "").strip()
            when = _parse_schedule(raw)
            if when is None:
                await message.reply(V.schedule_bad_time(raw), parse_mode=ParseMode.HTML)
                return
            await fsm.clear(message.from_user.id)
            await _schedule_publish(client, container, message, code, when)
        elif state == STATE_EDIT_FOOTER:
            from kurosoden.shared.settings_ui import parse_user_markup
            from nekofetch.services.footer_service import FooterService

            html = parse_user_markup(message)
            await fsm.clear(message.from_user.id)
            result = await FooterService(container).set_footer(html)
            await message.reply(
                V.footer_updated(result.ok, result.footers_rewritten,
                                 result.bots_bumped),
                parse_mode=ParseMode.HTML,
            )

    @client.on_message(filters.command("cancel"))
    async def _cancel(_: Client, message: Message) -> None:
        if message.from_user:
            await fsm.clear(message.from_user.id)
        await message.reply(f"{V.ICON} Cancelled.", parse_mode=ParseMode.HTML)

    # ── /publish — Review and publish flow ────────────────────────────────────
    @client.on_message(filters.command("publish"))
    async def _publish_cmd(_: Client, message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply(
                "<b>📰 Publish Review</b>\n\n"
                "Usage: <code>/publish REQ-XXXX</code>\n\n"
                "Shows the generated caption and thumbnail for review.\n"
                "You can edit the caption (Markdown or HTML) before publishing.",
                parse_mode=ParseMode.HTML,
            )
            return

        request_code = parts[1].strip()
        await _review_for_publish(client, container, message, request_code, fsm)

    # ── /recover — Channel recovery ───────────────────────────────────────────
    @client.on_message(filters.command("recover"))
    async def _recover_cmd(_: Client, message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply(
                "<b>🔄 Channel Recovery</b>\n\n"
                "Usage: <code>/recover REQ-XXXX</code>\n\n"
                "Detects and replaces banned distribution channels:\n"
                "• Replaces the distribution channel\n"
                "• Updates buttons in the main channel\n"
                "• Updates buttons in the index channel\n"
                "• Repairs every affected link",
                parse_mode=ParseMode.HTML,
            )
            return

        request_code = parts[1].strip()
        await _recover_channel(client, container, message, request_code)

    # ── /help ─────────────────────────────────────────────────────────────────
    @client.on_message(filters.command("help"))
    async def _help(_: Client, message: Message) -> None:
        caption = (
            "<b>🔮 Gojo Satoru — Publisher</b>\n\n"
            "<i>The final step — your work goes live here.</i>\n\n"
            "<b>How it works</b>\n"
            "1. Distribution finishes → a task lands with you\n"
            "2. I build the main-channel post + franchise thumbnail\n"
            "3. Review the caption — edit it in Markdown/HTML\n"
            "4. Approve → I publish now or on a schedule\n"
            "5. The A–Z index updates itself\n\n"
            "<b>Commands</b>\n"
            "/tasks — What's waiting to publish\n"
            "/publish — Review &amp; publish a title\n"
            "/schedule — Publish at a set time\n"
            "/recover — Rebuild a banned channel + fix every button\n"
            "/settings — Caption template, main channel, index"
        )
        await send_screen(
            client, message.chat.id,
            Screen(caption=caption, image=pick_artwork("gojo"),
                   keyboard=keyboard([("◀ Back", cb("gojo", "home"))])),
        )

    # ── /settings ── handled by the shared human-friendly settings engine
    # (register_settings in handlers/__init__.py) under the gojo|set|… namespace.
    # A local /settings handler here would shadow it — see the app.py note.


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _review_for_publish(
    client: Client, container: Container, message: Message,
    request_code: str, fsm: FSM,
) -> None:
    """Show the caption/thumbnail for admin review before publishing."""
    from nekofetch.infrastructure.database.postgres.session import session_scope
    from nekofetch.infrastructure.repositories.request_repo import RequestRepository

    async with session_scope(container.pg_sessionmaker) as session:
        req = await RequestRepository(session).get_by_code(request_code)
        if req is None:
            await message.reply(
                f"❌ <b>Request not found:</b> {request_code}",
                parse_mode=ParseMode.HTML,
            )
            return
        title = req.anime_title
        anime_doc_id = req.anime_doc_id

    await send_screen(
        client, message.chat.id,
        Screen(
            caption=V.review_card(title, request_code, anime_doc_id),
            image=pick_artwork("gojo"),
            keyboard=_publish_keyboard(request_code),
        ),
    )


async def _execute_publish(
    client: Client, container: Container, message: Message, request_code: str,
    *, caption_override: str | None = None, silent: bool = False,
) -> None:
    """Publish to the main channel and update the index.

    ``caption_override`` carries an admin-edited caption (already parsed to HTML
    with styling and line breaks preserved); ``silent`` posts without a channel
    notification. Both flow straight through ``PublishingService.publish``.
    """
    try:
        from nekofetch.services.publishing_service import PublishingService

        title = request_code
        try:
            from nekofetch.infrastructure.database.postgres.session import session_scope
            from nekofetch.infrastructure.repositories.request_repo import RequestRepository
            async with session_scope(container.pg_sessionmaker) as session:
                req = await RequestRepository(session).get_by_code(request_code)
                if req:
                    title = req.anime_title
        except Exception:  # noqa: BLE001 — title is decorative on the receipt
            pass

        await PublishingService(container).publish(
            request_code, caption_override=caption_override, silent=silent,
        )

        await send_screen(
            client, message.chat.id,
            Screen(caption=V.published(title, silent=silent),
                   image=pick_artwork("gojo"),
                   keyboard=keyboard([(V.BTN_TASKS, cb("gojo", "tasks"))])),
        )

        # Mark task as completed.
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine
        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        await engine.complete_task(request_code, "gojo")

    except Exception as exc:
        log.warning("gojo.publish.failed", code=request_code, error=str(exc))
        # ``message`` may be a Message (has .reply) or a bare Chat (scheduled
        # fire) — resolve a chat id either way and send through the client.
        chat_id = getattr(message, "chat", message)
        chat_id = getattr(chat_id, "id", chat_id)
        await client.send_message(
            chat_id, V.fail(str(exc)[:300]), parse_mode=ParseMode.HTML,
        )


async def _recover_channel(
    client: Client, container: Container, message: Message, request_code: str,
) -> None:
    """Recover a banned or broken distribution channel."""
    from nekofetch.infrastructure.database.postgres.session import session_scope
    from nekofetch.infrastructure.repositories.request_repo import RequestRepository

    async with session_scope(container.pg_sessionmaker) as session:
        req = await RequestRepository(session).get_by_code(request_code)
        if req is None:
            await message.reply(
                f"❌ <b>Request not found:</b> {request_code}",
                parse_mode=ParseMode.HTML,
            )
            return
        title = req.anime_title
        anime_doc_id = req.anime_doc_id

    if not anime_doc_id:
        await message.reply("❌ No anime ID found for this request.")
        return

    await message.reply(
        f"🔄 <b>Starting recovery</b> for <b>{title}</b>...\n\n"
        "<i>Checking distribution channels...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        # Reuse NekoFetch's BotOrchestratorService for recreation.
        from nekofetch.services.bot_orchestrator import BotOrchestratorService

        orch = BotOrchestratorService(container)
        info = await orch.recreate_bot(anime_doc_id)

        if info:
            await message.reply(
                f"✅ <b>Channel Recovered!</b>\n\n"
                f"🎬 <b>Anime:</b> {title}\n"
                f"📺 <b>New entity:</b> @{info.username or info.name}\n\n"
                "<i>All buttons in the main channel and index have been updated.</i>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.reply(
                f"⚠️ <b>Recovery incomplete</b>\n\n"
                "Could not recreate the distribution entity.\n"
                "Check the logs for details.",
                parse_mode=ParseMode.HTML,
            )
    except Exception as exc:
        await message.reply(
            f"❌ <b>Recovery failed:</b> {str(exc)[:300]}",
            parse_mode=ParseMode.HTML,
        )


# ── Scheduling ─────────────────────────────────────────────────────────────────


def _parse_schedule(raw: str) -> datetime | None:
    """Parse ``YYYY-MM-DD HH:MM`` into a future ``datetime``, or ``None``.

    Server-local time. Anything unparseable or already in the past returns
    ``None`` so the caller can show the "bad time" prompt.
    """
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            when = datetime.strptime(raw.strip(), fmt)
            break
        except ValueError:
            when = None
    if when is None:
        return None
    if when <= datetime.now():
        return None
    return when


async def _schedule_publish(
    client: Client, container: Container, message: Message,
    request_code: str, when: datetime,
) -> None:
    """Register an APScheduler one-shot that publishes ``request_code`` at ``when``.

    Reuses the same ``_execute_publish`` path the buttons use, so a scheduled
    publish is byte-identical to an immediate one — just deferred.
    """
    scheduler = getattr(container, "scheduler", None)
    if scheduler is None:
        await message.reply(V.fail("scheduler unavailable"), parse_mode=ParseMode.HTML)
        return

    chat_id = message.chat.id

    async def _fire() -> None:
        # Build a minimal stand-in so _execute_publish can reply into the chat.
        try:
            await _execute_publish(
                client, container,
                await client.get_chat(chat_id), request_code, silent=False,
            )
        except Exception as exc:  # noqa: BLE001 — a scheduled fire must never crash the loop
            log.warning("gojo.schedule.fire_failed", code=request_code, error=str(exc))

    title = request_code
    try:
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.repositories.request_repo import RequestRepository
        async with session_scope(container.pg_sessionmaker) as session:
            req = await RequestRepository(session).get_by_code(request_code)
            if req:
                title = req.anime_title
    except Exception:  # noqa: BLE001
        pass

    scheduler.at(when, _fire, id=f"gojo-publish-{request_code}")
    await send_screen(
        client, message.chat.id,
        Screen(caption=V.scheduled(title, when.strftime("%Y-%m-%d %H:%M")),
               image=pick_artwork("gojo"),
               keyboard=keyboard([(V.BTN_TASKS, cb("gojo", "tasks"))])),
    )
