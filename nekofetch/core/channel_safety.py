"""Safety helpers for wiping a control-center channel before a rebuild.

The log channel (control center) and the thumbnail channel are managed
machines: every section is a tracked message that gets edited in place
or re-posted on startup. The previous wipe only deleted tracked message
ids + a sweep pass that filtered on ``from_user.is_self``. That left
admin-typed notes and failure-card echoes lingering after a rebuild.

The user requested that EVERY message in the channel be cleared on a
restart — including their own typing, other admins' messages, and any
message from a different bot / user — so the rebuild lands on a clean
slate. Doing that naively is dangerous:

  * Telegram history is unbounded — accidentally deleting weeks of older
    history would be unrecoverable.
  * Mass deletion triggers ``FloodWait`` quickly.
  * Some messages (pinned dashboard, intro cover image) genuinely
    should NOT be touched.

This module provides a safe full-wipe that:

  1. Anchors the deletion to a known ``intro_id`` — only messages with
     ``msg.id > intro_id`` are touched. Anything older is preserved.
  2. Skips pinned message ids passed in via ``preserve_pinned_ids``.
  3. Caps the sweep at ``max_history`` messages (default 200) so a single
     fetch never escalates into runaway deletion.
  4. Chunks deletions 100 ids per call (Telegram's per-call cap) with a
     small sleep between chunks to dodge flood-wait.
  5. Logs every wipe with the deleted count so operators can audit.

Both :class:`nekofetch.services.log_channel_service.LogChannelService` and
:class:`nekofetch.services.thumbnail_channel_service.ThumbnailChannelService`
use this helper when their respective ``wipe_all_on_rebuild`` config
flag is True (default). Set the flag False to restore the original
"delete only tracked / bot-self messages" behaviour.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from nekofetch.core.logging import get_logger

log = get_logger(__name__)


# Substrings that mark an exception as Telegram refusing us because we are
# a Bot account (not a User). Pyrogram wraps the underlying Telegram API
# error in BadMsgNotification; the body carries either the literal
# BOT_METHOD_INVALID code or an in-flight "messages.GetHistory" mention.
# Both call sites — log_channel_service._wipe_all's bot-self sweep AND
# safe_full_channel_wipe — consult this helper so they log the same clear
# "channel_wipe.skipped_bot_client" warning instead of the generic
# "history_failed" that operators cannot distinguish from a transient
# network blip. Matched by substring (rather than imported pyrogram error
# classes) so this module stays easy to test and free of a pyrogram import
# dependency.
_BOT_METHOD_INVALID_MARKERS = (
    "BOT_METHOD_INVALID",
    "messages.GetHistory",
)


def is_bot_method_invalid(exc: BaseException) -> bool:
    """True when Telegram refused the API call because the caller is a Bot.

    Bots cannot call ``messages.getHistory`` (Telegram returns
    ``[400 BOT_METHOD_INVALID]``), so any iteration over a channel's
    history via a bot client will trip this guard. The caller is expected
    to surface a clear ``channel_wipe.skipped_bot_client`` warning so the
    operator knows the full-channel sweep was elided (but the tracked-id
    delete path above it still ran).
    """
    s = str(exc)
    return any(marker in s for marker in _BOT_METHOD_INVALID_MARKERS)


async def safe_full_channel_wipe(
    client,
    channel_id: int,
    *,
    intro_id: int | None,
    max_history: int = 200,
    preserve_pinned_ids: Iterable[int] = (),
    userbot_client=None,
) -> int:
    """Delete EVERY non-pinned message in ``channel_id`` newer than ``intro_id``.

    Returns the number of messages actually deleted. 0 means either nothing
    was eligible or the sweep was skipped.

    Safety rails:
      * ``intro_id`` is the floor — never delete anything older.
      * ``max_history`` caps the sweep count (Telegram caps single fetches
        at 200 anyway but making it explicit guards against future drift).
      * ``preserve_pinned_ids`` are skipped even if they fall in range.
      * Chunk-size 100 + 1.5s sleep avoids Telegram flood-wait.
      * Each delete chunk is wrapped in try/except so a single bad id
        does not abort the reset of the wipe.

    ``userbot_client`` (optional): a USER account from
    :class:`nekofetch.sources.telegram.userbot.UserbotPool`. When supplied,
    history iteration goes through it because Telegram forbids bots from
    calling ``messages.getHistory`` (``[400 BOT_METHOD_INVALID]``). The
    delete path still uses the bot ``client`` because bots CAN call
    ``delete_messages``. When the userbot is not provided (older set-up
    without a userbot session), the helper falls back to ``client`` and
    surfaces a distinct ``channel_wipe.skipped_bot_client`` warning so the
    operator can either provision a userbot or set ``wipe_all_on_rebuild
    = false`` in config to skip the full sweep entirely.
    """
    if intro_id is None:
        # Without an anchor we cannot safely bound the wipe. Caller decides
        # whether to skip or to fall back to the legacy bot-only sweep by
        # not setting ``wipe_all_on_rebuild`` in the first place.
        log.warning("channel_wipe.no_intro", channel_id=channel_id)
        return 0

    preserve_set = set(int(x) for x in preserve_pinned_ids if x)

    # 1. Collect every eligible message id. Pick the iterator that can
    #    actually call getHistory on this Telegram account type:
    #    user > bot (bots are refused with [400 BOT_METHOD_INVALID]).
    fetcher = userbot_client if userbot_client is not None else client

    to_delete: list[int] = []
    try:
        async for msg in fetcher.get_chat_history(channel_id, limit=max_history):
            try:
                mid = int(msg.id)
            except Exception:  # noqa: BLE001
                continue
            # Telegram message ids are monotonically increasing per chat,
            # so anything <= intro_id is part of pre-loaded history.
            if mid <= intro_id:
                continue
            if mid in preserve_set:
                continue
            to_delete.append(mid)
    except Exception as exc:  # noqa: BLE001
        # Distinguishing Bot-Forbidden vs Transient matters to the operator:
        # the channel-wipe path runs every restart from a bot client (the
        # admin bot) and Telegram forbids ``messages.getHistory`` for bots;
        # a generic 'history_failed' warning hides that fact from the logs
        # and the operator's Slack/pm'd alerts. Emit a distinct log event
        # the operator can grep for, and tell them the tracked-id delete
        # path above still ran.
        if is_bot_method_invalid(exc):
            log.warning(
                "channel_wipe.skipped_bot_client",
                channel_id=channel_id,
                hint=(
                    "admin_client is a Bot; Telegram forbids GetHistory on "
                    "bots. Configure TELEGRAM_USERBOT_SESSION in .env and "
                    "restart — UserbotPool will then iterate history here. "
                    "Tracked message-IDs above were still deleted."
                ),
            )
        else:
            # Telegram occasionally raises on the first history fetch after
            # a channel swap; surface but never fail the calling rebuild.
            log.warning(
                "channel_wipe.history_failed", channel_id=channel_id, error=str(exc),
            )
        return 0

    if not to_delete:
        return 0

    # 2. Chunk into 100-id slices (Telegram per-call cap) and delete with
    #    a sleep between each chunk so we don't trip flood-wait.
    deleted = 0
    chunk_size = 100
    for chunk_start in range(0, len(to_delete), chunk_size):
        chunk = to_delete[chunk_start: chunk_start + chunk_size]
        try:
            await client.delete_messages(channel_id, chunk)
            deleted += len(chunk)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "channel_wipe.chunk_failed",
                channel_id=channel_id,
                chunk_size=len(chunk),
                error=str(exc),
            )
        await asyncio.sleep(1.5)

    log.info(
        "channel_wipe.done",
        channel_id=channel_id,
        deleted=deleted,
        eligible=len(to_delete),
        intro_id=intro_id,
        max_history=max_history,
    )
    return deleted
