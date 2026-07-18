"""Force-join gate for Lelouch — requesting is allowed only for channel members.

Browsing the bot (home, help, my-requests) stays open; the gate fires only when
a user tries to *make* a request (``req|new`` and the title-search entry). Staff
bypass entirely. Reuses :mod:`nekofetch.bots.force_sub` for the actual
membership check (which fails *open* on operator misconfig, so a bad channel id
never locks everyone out) and dresses the prompt in Lelouch's voice.
"""

from __future__ import annotations

from typing import Any

from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from nekofetch.bots.force_sub import channels_to_join
from nekofetch.core.logging import get_logger
from nekofetch.ui.screens import card, send_screen
from kurosoden.shared import lelouch_voice as V

log = get_logger(__name__)

# The recheck button routes back through the intake entry the caller names, so a
# freshly-joined user flows straight into title entry with no extra taps.
RECHECK_NEW = "req|new"


def _join_card(channels: list[tuple[str, str | None]], recheck_cb: str):
    """A Lelouch-voiced join prompt: channel links + a recheck button."""
    caption = f"{V.JOIN_TITLE}\n\n{V.JOIN_BODY}"
    url_rows = [[(f"➜ Join {title}", url)] for title, url in channels if url]
    return card(
        caption,
        bot_name="lelouch",
        url_buttons=url_rows,
        buttons=[[(V.BTN_RECHECK, recheck_cb)]],
    )


async def ensure_can_request(
    client: Client,
    container: Any,
    user_id: int,
    chat_id: int,
    *,
    is_staff: bool = False,
    old_msg=None,
    recheck_cb: str = RECHECK_NEW,
) -> bool:
    """Return True if ``user_id`` may proceed to request.

    When channels are still unjoined, sends the Lelouch join card and returns
    False. Staff always pass. Any failure in the membership check itself fails
    *open* (returns True) so the gate never becomes an accidental lockout.
    """
    if is_staff:
        return True
    try:
        pending = await channels_to_join(client, container, user_id)
    except Exception:  # noqa: BLE001 — never let the gate itself block a request
        log.warning("lelouch.join_gate.check_failed", user=user_id)
        return True
    if not pending:
        return True
    await send_screen(client, chat_id, _join_card(pending, recheck_cb),
                      old_msg=old_msg)
    return False
