"""Shared bot UI helpers — sticker → staged-loading → welcome-screen pattern.

Used by all four Kuro Sōden pipeline bots so their /start feels consistent
and NekoFetch-rich. Centralises the start-flow so keyboard layouts,
delays, artwork char-pools, and failure modes stay uniform — when a bot
crashes on its sticker or artwork, it doesn't surface a scary traceback
to the user.

Single entry point: :func:`send_rich_welcome`.

Pattern (mirrors NekoFetch's admin bot at
``nekofetch.bots.admin.handlers.start``):

    1. ``send_sticker`` with ``ui_cfg.start_sticker_id`` (best-effort)
    2. reply ``🎬 loading…`` placeholder
    3. ``staged_loading`` animates it through Connecting / Loading / Verifying
    4. ``sticker_delete_delay`` pause (≈1.5s)
    5. delete sticker + loading message
    6. ``send_screen(client, chat_id, screen)`` with the bot's pre-built
       Screen (caption + per-character artwork via ``pick_artwork(bot_name)``
       + inline keyboard).

Everything is wrapped in try/except so a single broken asset (sticker
file_id, image fetch, network blip) cannot abort the user's first
interaction.
"""

from __future__ import annotations

import asyncio

from pyrogram import Client
from pyrogram.types import Message

from nekofetch.core.container import Container
from nekofetch.ui.screens import Screen, send_screen


async def send_rich_welcome(
    client: Client,
    container: Container,
    message: Message,
    screen: Screen,
) -> None:
    """Theatrical /start: sticker → loading animation → welcome screen.

    Args:
        client: Pyrogram client (the bot).
        container: Kage container — pulls ``UIConfig`` for sticker id,
            sticker-delete delay, and loading-animation timing.
        message: The inbound ``/start`` message.
        screen: Pre-built :class:`nekofetch.ui.screens.Screen` holding the
            caption, bot-specific image (``pick_artwork(bot_name)``), and
            inline keyboard. The helper does NOT modify it; caller owns it.
    """
    from pyrogram.enums import ParseMode

    ui_cfg = container.config.ui
    chat_id = message.chat.id

    # ── 1. Sticker (best-effort; some deployments lack a sticker id) ──
    sticker = None
    sticker_id = ui_cfg.start_sticker_id
    if sticker_id:
        try:
            sticker = await client.send_sticker(chat_id, sticker_id)
        except Exception:
            sticker = None

    # ── 2. Loading placeholder ─────────────────────────────────────────
    msg = await message.reply(
        "🎬 <b>loading…</b>", parse_mode=ParseMode.HTML,
    )

    # ── 3. Animated loading animation from NekoFetch ───────────────────
    try:
        from nekofetch.localization.messages import M, t
        from nekofetch.ui.progress import staged_loading

        await staged_loading(
            msg,
            [t(M.LOADING_STAGE_CONNECTING), t(M.LOADING_STAGE_LOADING),
             t(M.LOADING_STAGE_VERIFYING)],
            delay_per_stage=ui_cfg.loading_dot_delay * 3,
        )
    except Exception:
        # If staged_loading errors (animation step failed), just sleep
        # briefly so the sticker still has a moment on screen.
        await asyncio.sleep(0.5)

    # ── 4. Cleanup intermediate messages (sequential so no race) ──────
    await asyncio.sleep(ui_cfg.sticker_delete_delay)
    if sticker is not None:
        try:
            await sticker.delete()
        except Exception:
            pass
    try:
        await msg.delete()
    except Exception:
        pass

    # ── 5. The actual welcome screen ────────────────────────────────────
    await send_screen(client, chat_id, screen)
