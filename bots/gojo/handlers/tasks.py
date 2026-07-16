"""Gojo task handlers — REUSES NekoFetch's publishing infrastructure.

Key principle: Gojo does NOT reimplement publishing. It delegates to:
  • MainChannelService.publish() — generates and posts to the main channel.
  • IndexChannelService.refresh_letter() — updates the A-Z index.
  • PublishingService.publish() — the full publish orchestration.
  • BotOrchestratorService — recreates bots for channel recovery.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.localization.messages import t
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.screens import Screen, send_screen

log = get_logger(__name__)

STATE_EDIT_CAPTION = "gojo:await_caption_edit"


def register(client: Client, container: Container) -> None:
    fsm = FSM(container.redis, bot="gojo")

    # ── /tasks — View assigned publishing tasks ───────────────────────────────
    @client.on_message(filters.command("tasks"))
    async def _tasks(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        from kage.shared.admin_assignment import AdminAssignmentEngine
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
        await _execute_publish(client, container, q.message, code)

    @client.on_callback_query(filters.regex(r"^gojo\|publish_edit\|"))
    async def _cb_edit(_: Client, q: CallbackQuery) -> None:
        _, _, code = q.data.split("|", 2)
        await q.answer()
        await fsm.set(q.from_user.id, STATE_EDIT_CAPTION, request_code=code)
        await q.message.reply(
            "<b>✏️ Edit Caption</b>\n\n"
            "Send the edited caption (Markdown or HTML format).\n"
            "Use /cancel to abort.",
            parse_mode=ParseMode.HTML,
        )

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

    # ── /schedule — Schedule a post ───────────────────────────────────────────
    @client.on_message(filters.command("schedule"))
    async def _schedule_cmd(_: Client, message: Message) -> None:
        await message.reply(
            "<b>📅 Schedule Publication</b>\n\n"
            "Usage: <code>/schedule REQ-XXXX YYYY-MM-DD HH:MM</code>\n\n"
            "<i>Scheduling will be available in a future update. "
            "Use /publish for immediate publishing.</i>",
            parse_mode=ParseMode.HTML,
        )

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

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
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

    # Show a preview with publish/edit buttons.
    markup = keyboard([
        [("🚀 Publish Now", cb("gojo", "publish_confirm", request_code)),
         ("✏️ Edit Caption", cb("gojo", "publish_edit", request_code))],
        [("❌ Cancel", cb("gojo", "home"))],
    ])

    caption_preview = (
        f"<b>📰 Ready to Publish</b>\n\n"
        f"📋 <b>Request:</b> <code>{request_code}</code>\n"
        f"🎬 <b>Anime:</b> {title}\n"
        f"🆔 <b>ID:</b> <code>{anime_doc_id or '—'}</code>\n\n"
        "<i>Review the content below and choose:</i>\n"
        "<b>Publish Now</b> — immediately publish to the main channel.\n"
        "<b>Edit Caption</b> — send a modified version (Markdown/HTML)."
    )

    await message.reply(
        caption_preview,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )


async def _execute_publish(
    client: Client, container: Container, message: Message, request_code: str,
) -> None:
    """Publish to the main channel and update the index."""
    try:
        # Reuse NekoFetch's PublishingService for the full publish flow.
        from nekofetch.services.publishing_service import PublishingService

        count = await PublishingService(container).publish(request_code)

        await message.reply(
            f"✅ <b>Published Successfully!</b>\n\n"
            f"📋 Request: <code>{request_code}</code>\n"
            f"📦 Files: {count}\n\n"
            "<i>Main channel post created. Index updated.</i>",
            parse_mode=ParseMode.HTML,
        )

        # Mark task as completed.
        from kage.shared.admin_assignment import AdminAssignmentEngine
        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        await engine.complete_task(request_code, "gojo")

    except Exception as exc:
        log.warning("gojo.publish.failed", code=request_code, error=str(exc))
        await message.reply(
            f"❌ <b>Publish failed:</b> {str(exc)[:300]}",
            parse_mode=ParseMode.HTML,
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
