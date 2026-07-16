"""Levi task handlers — REUSES NekoFetch's existing download infrastructure.

Key principle: Levi does NOT reimplement downloading. It delegates to:
  • ``QueueService`` for enqueuing jobs (picked up by DownloadWorker).
  • ``RequestService`` for updating source assignment.
  • ``SourceRegistry.available()`` for listing sources.
  • ``DownloadWorker`` (background loop) for actual downloading.
  • ``ProcessingPipeline`` for post-download processing.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import RequestStatus
from nekofetch.localization.messages import t
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import Screen, send_screen

log = get_logger(__name__)

STATE_SOURCE = "levi:await_source"
STATE_THUMBNAIL = "levi:await_thumbnail"
STATE_HEADER = "levi:await_header_edit"


def register(client: Client, container: Container) -> None:
    """Register Levi's handlers — source selection, queuing, thumbnails."""
    fsm = FSM(container.redis, bot="levi")

    # ── /tasks — View assigned download tasks ──────────────────────────────
    @client.on_message(filters.command("tasks"))
    async def _tasks(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        from kage.shared.admin_assignment import AdminAssignmentEngine

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        active = await engine.get_active_tasks(message.from_user.id)

        if not active:
            await message.reply(
                "<b>⚔️ No active download tasks.</b>\n\n"
                "No anime assigned to you for downloading right now.",
                parse_mode=ParseMode.HTML,
            )
            return

        lines = ["<b>⚔️ Your Download Tasks</b>\n"]
        for a in active[:10]:
            status_icon = "🔄" if a.status == "in_progress" else "⏳"
            # Fetch request title
            from nekofetch.infrastructure.database.postgres.session import session_scope
            from nekofetch.infrastructure.repositories.request_repo import RequestRepository

            title = a.request_code  # fallback
            try:
                async with session_scope(container.pg_sessionmaker) as s:
                    req = await RequestRepository(s).get_by_code(a.request_code)
                    if req:
                        title = req.anime_title
            except Exception:
                pass

            lines.append(
                f"{status_icon} <code>{a.request_code}</code> — <b>{title}</b>"
            )

        await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── /sources — Browse available download sources ───────────────────────
    @client.on_message(filters.command("sources"))
    async def _sources(_: Client, message: Message) -> None:
        available = container.sources.available()
        cfg_sources = container.config.sources.enabled

        lines = ["<b>📡 Available Download Sources</b>\n"]
        for name in cfg_sources:
            active = "✅" if name in available else "❌"
            lines.append(f"{active} <b>{name}</b>")

        lines.append(
            "\n<i>Admins choose the source manually — no auto-fallback.</i>\n\n"
            "<b>To assign a source:</b> reply with <code>/assign REQ-XXXX source_name</code>"
        )
        await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)

    # ── /assign — Assign source to a request and queue it ──────────────────
    @client.on_message(filters.command("assign"))
    async def _assign(_: Client, message: Message) -> None:
        if not message.from_user:
            return

        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3:
            await message.reply(
                "<b>⚔️ Assign Source</b>\n\n"
                "Usage: <code>/assign REQ-XXXX source_name</code>\n\n"
                "<b>Available sources:</b>\n"
                + "\n".join(f"• <b>{s}</b>" for s in container.sources.available()),
                parse_mode=ParseMode.HTML,
            )
            return

        request_code = parts[1].strip()
        source_name = parts[2].strip().lower()

        # Validate source exists.
        if source_name not in container.sources.available():
            await message.reply(
                f"❌ <b>Unknown source:</b> {source_name}\n\n"
                f"Available: {', '.join(container.sources.available())}",
                parse_mode=ParseMode.HTML,
            )
            return

        await _assign_source_and_queue(
            client, container, message, request_code, source_name
        )

    # ── Callback: source selection from inline buttons ─────────────────────
    @client.on_callback_query(filters.regex(r"^levi\|source\|"))
    async def _cb_source(_: Client, q: CallbackQuery) -> None:
        _, _, request_code, source_name = q.data.split("|", 3)
        await q.answer()
        await _assign_source_and_queue(
            client, container, q.message, request_code, source_name
        )
        # Delete the source selection message to keep chat clean.
        try:
            await q.message.delete()
        except Exception:
            pass

    # ── /header — Generate header from template ────────────────────────────
    @client.on_message(filters.command("header"))
    async def _header(_: Client, message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.reply(
                "<b>🏷️ Header Generation</b>\n\n"
                "Usage: <code>/header REQ-XXXX</code>\n\n"
                "Generates the default header using the configured template.",
                parse_mode=ParseMode.HTML,
            )
            return

        request_code = parts[1].strip()
        await _generate_header(client, container, message, request_code)

    # ── Photo handler — manual thumbnail upload ────────────────────────────
    @client.on_message(filters.photo & filters.private)
    async def _photo_handler(_: Client, message: Message) -> None:
        if not message.from_user or not message.photo:
            return

        state, data = await fsm.get(message.from_user.id)
        if state != STATE_THUMBNAIL:
            return  # Not expecting a thumbnail — ignore.

        file_path = await client.download_media(
            message.photo.file_id,
            file_name=str(
                container.env.storage_path
                / "thumbnails"
                / f"levi_{message.photo.file_unique_id}.jpg"
            ),
        )

        if file_path:
            await message.reply(
                "✅ <b>Thumbnail received!</b>\n\n"
                "Use <code>/header REQ-XXXX</code> to generate the header.",
                parse_mode=ParseMode.HTML,
            )
            await fsm.set(
                message.from_user.id,
                "levi:header_ready",
                thumbnail_path=str(file_path),
                request_code=data.get("request_code", ""),
            )


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _assign_source_and_queue(
    client: Client,
    container: Container,
    message: Message,
    request_code: str,
    source_name: str,
) -> None:
    """Assign a source to a request and enqueue it for download.

    Reuses: RequestService.update_source() then creates a DownloadJob
    so NekoFetch's DownloadWorker (background loop) picks it up.
    """
    from nekofetch.services.request_service import RequestService
    from nekofetch.infrastructure.database.postgres.session import session_scope
    from nekofetch.infrastructure.database.postgres.models import DownloadJob
    from nekofetch.infrastructure.repositories.request_repo import RequestRepository
    from nekofetch.domain.enums import RequestStatus, JobStatus

    try:
        # 1. Update the source on the request.
        req = await RequestService(container).update_source(request_code, source_name)

        # 2. Create a DownloadJob so the background DownloadWorker picks it up.
        #    (QueueService doesn't have a standalone enqueue() — the review
        #    handler creates DownloadJob rows directly, which is what we do.)
        async with session_scope(container.pg_sessionmaker) as session:
            repo = RequestRepository(session)
            db_req = await repo.get_by_code(request_code)
            if db_req is not None:
                db_req.status = RequestStatus.QUEUED
                job = DownloadJob(
                    request_id=db_req.id,
                    status=JobStatus.QUEUED,
                    priority=100,
                )
                session.add(job)
                await session.flush()
                # Detach so we can read attributes after session closes.
                title = db_req.anime_title
                session.expunge(db_req)

        # 3. Confirm to admin.
        msg = (
            f"✅ <b>Source Assigned & Queued!</b>\n\n"
            f"📋 <b>Request:</b> <code>{request_code}</code>\n"
            f"📡 <b>Source:</b> <b>{source_name}</b>\n"
            f"🎬 <b>Anime:</b> {title}\n\n"
            f"<i>The download worker will pick this up automatically.</i>\n\n"
            f"<b>Next steps:</b>\n"
            f"• Upload a 1:1 square thumbnail image\n"
            f"• Use <code>/header {request_code}</code> to generate the header"
        )
        await message.reply(msg, parse_mode=ParseMode.HTML)

        # 4. Prompt for thumbnail.
        await message.reply(
            "🖼️ <b>Upload Thumbnail</b>\n\n"
            "Send a <b>1:1 square image</b> to use as the thumbnail.\n"
            "<i>This will be used for the header/franchise card.</i>",
            parse_mode=ParseMode.HTML,
        )

        # 5. Set FSM state so the photo handler picks it up.
        from nekofetch.bots.fsm import FSM
        fsm = FSM(container.redis, bot="levi")
        await fsm.set(
            message.from_user.id,
            STATE_THUMBNAIL,
            request_code=request_code,
        )

    except Exception as exc:
        log.warning("levi.assign.failed", code=request_code, source=source_name, error=str(exc))
        await message.reply(
            f"❌ <b>Failed to assign source:</b> {str(exc)[:200]}",
            parse_mode=ParseMode.HTML,
        )


async def _generate_header(
    client: Client,
    container: Container,
    message: Message,
    request_code: str,
) -> None:
    """Generate the default header using the configured template."""
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
        # Extract fields inside session to avoid DetachedInstanceError.
        title = req.anime_title
        source = req.source or "Unknown"

    # Use the storage channel header template from config.
    template = container.config.storage_channel.header_template
    header = template.format(
        title=title,
        season="1",
        resolution="Multi",
        language="Sub & Dub",
        content_type="TV",
        episode_from="1",
        episode_to="?",
        group=source,
    )

    # Show the generated header and ask for edits.
    markup = keyboard([
        ("✅ Approve", cb("levi", "header_ok", request_code)),
        ("✏️ Edit (Markdown/HTML)", cb("levi", "header_edit", request_code)),
    ])

    await message.reply(
        f"<b>🏷️ Generated Header</b>\n\n"
        f"<b>Request:</b> <code>{request_code}</code>\n"
        f"<b>Anime:</b> {title}\n\n"
        f"<b>Preview:</b>\n"
        f"<blockquote>{header}</blockquote>\n\n"
        f"<i>Approve or send an edited version (Markdown or HTML).</i>",
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )
