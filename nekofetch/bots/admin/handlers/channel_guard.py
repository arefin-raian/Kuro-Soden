"""Keep the bot-managed channels clean.

When a staff member posts an ordinary message (text, sticker, photo, etc.) in the
log channel or thumbnail channel that the bot didn't expect, it's deleted immediately —
UNLESS the sender is the admin currently on duty for that channel. The on-duty admin
needs to be able to reply (slug mapping, franchise edits, etc.) without interference
from off-duty staff.

Commands and the bot's own posts are always ignored.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

log = get_logger(__name__)

# Map Telegram channel ids to shift channel keys.
_CHANNEL_MAP: dict[int, str] = {}


def register(client: Client, container: Container) -> None:
    cfg = container.config

    # Collect channel ids to guard.
    guarded: set[int] = set()
    if cfg.log_channel.enabled and cfg.log_channel.channel_id:
        guarded.add(cfg.log_channel.channel_id)
        _CHANNEL_MAP[cfg.log_channel.channel_id] = "logcc"
    if cfg.thumbnail_channel.enabled and cfg.thumbnail_channel.channel_id:
        guarded.add(cfg.thumbnail_channel.channel_id)
        _CHANNEL_MAP[cfg.thumbnail_channel.channel_id] = "thumbcc"

    if not guarded:
        return

    @client.on_message(filters.chat(list(guarded)), group=9)
    async def _guard_channel(_: Client, message: Message) -> None:
        # Ignore everything bot-managed or non-conversational:
        #  - our own posts (cards, sections, dividers) are "outgoing"
        #  - pin/join service notices
        #  - slash commands (allow staff to use commands in the channel if needed)
        if getattr(message, "outgoing", False) or getattr(message, "service", None):
            return
        if message.from_user and getattr(message.from_user, "is_self", False):
            return
        if message.text and message.text.startswith("/"):
            return

        # A channel flow is waiting for a typed reply here (AniZone slugs, a
        # franchise-mapping edit). Anonymous admins post AS the channel, so this
        # message has no ``from_user`` and the per-user FSM below can't see it —
        # the chat-scoped marker is the only thing that identifies it as the
        # awaited reply. While the marker is armed, never delete on arrival: the
        # consuming handler disarms + deletes it once it's been read, so the
        # channel still ends up clean. Deleting here would race the handler and
        # eat the reply before it lands (the bug this guards against).
        from nekofetch.bots.channel_reply import is_armed
        if await is_armed(container.redis, message.chat.id):
            return

        # Allow the on-duty admin to post replies (slug mapping, franchise edits,
        # manual-upload workflow, etc.). Off-duty admins get their messages deleted
        # so they can't interfere with the active shift.
        if message.from_user:
            # If the admin is mid-flow in a reply-expecting state, this message IS
            # the awaited reply (an AniZone slug list, a franchise edit, a custom
            # resolution). Never delete it here — the consuming handler deletes it
            # AFTER it has been read, so the channel still ends up clean. Deleting
            # on arrival would race the handler and eat the reply before it lands.
            from nekofetch.bots.fsm import FSM
            from nekofetch.core.constants import REPLY_EXPECTING_STATES

            state, _ = await FSM(container.redis, bot="admin").get(message.from_user.id)
            if state in REPLY_EXPECTING_STATES:
                return

            shift_key = _CHANNEL_MAP.get(message.chat.id)
            if shift_key:
                from nekofetch.services.shift_service import ShiftService
                shift = ShiftService(container)
                can, _reason = await shift.can_act(shift_key, message.from_user.id)
                if can:
                    return  # on-duty admin — allow the message through

        # Everything else is unexpected human chatter - delete it quietly.
        try:
            await message.delete()
        except Exception as exc:
            log.debug("channel_guard.delete.failed",
                      chat_id=message.chat.id, error=str(exc))
