"""Wires thumbnail channel callbacks into the admin bot.

All callback routing is handled by a single generic handler that delegates
to ``ThumbnailChannelService.handle_callback()``, which routes internally
to pick_logo, pick_poster, pick_bg, select_num, generate, open, refresh.

No FSM or text-reply handling needed — admins select assets by tapping inline
numbered buttons (1, 2, 3, ...) generated alongside the Telegraph gallery link.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.services.thumbnail_channel_service import ThumbnailChannelService

log = get_logger(__name__)


def register(client: Client, container: Container) -> None:
    thumb_svc = ThumbnailChannelService(container)

    async def _check_shift(q: CallbackQuery) -> bool:
        """Verify the user is allowed to act on Asset Forge (thumbnail channel).
        The owner always bypasses."""
        from nekofetch.services.shift_service import ShiftService
        from nekofetch.ui.duty_board import blocked_alert
        shift_svc = ShiftService(container)
        user_id = q.from_user.id
        can, reason = await shift_svc.can_act("thumbcc", user_id)
        if can:
            return True
        await q.answer(blocked_alert(reason, "thumbcc"), show_alert=True)
        return False

    @client.on_callback_query(filters.regex(r"^thumb\|"), group=2)
    async def _thumbnail_callback(_c: Client, q: CallbackQuery) -> None:
        """Route all ``thumb|*`` callbacks to ThumbnailChannelService.

        Shift-aware: only the on-duty worker (or owner) can interact with
        the Asset Forge channel. Internal routing handled by
        ``handle_callback()``.
        """
        if not await _check_shift(q):
            return
        try:
            handled = await thumb_svc.handle_callback(q)
            if not handled:
                await q.answer("Unknown thumbnail action.", show_alert=True)
        except Exception as exc:
            log.warning("thumb.handler.failed", error=str(exc))
            await q.answer("Something went wrong.", show_alert=True)

    async def _in_thumbnail_channel(_flt, _cli, message: Message) -> bool:
        """Match only images posted to the configured Asset Forge channel.

        Read dynamically (not bound at register time) so a channel id set or
        changed via settings after startup is still honoured."""
        cid = container.config.thumbnail_channel.channel_id
        return bool(cid) and message.chat is not None and message.chat.id == cid

    @client.on_message(
        (filters.photo | filters.document) & filters.create(_in_thumbnail_channel),
        group=2,
    )
    async def _thumbnail_upload(_c: Client, message: Message) -> None:
        """Consume an image posted to the Asset Forge channel when an upload is
        armed (the on-duty worker tapped "⬆️ Upload my own"). No-op otherwise."""
        try:
            await thumb_svc.handle_uploaded_image(message)
        except Exception as exc:  # noqa: BLE001
            log.warning("thumb.upload.failed", error=str(exc))
