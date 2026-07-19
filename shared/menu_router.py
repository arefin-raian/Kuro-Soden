"""Shared menu router helper for all four Kuro Soden pipeline bots.

Built so every key-press on an inline button produces a beautiful, helpful
screen instead of the previous "Type /X in chat" dead toast.

* :func:`tool_screen` — usage / how-it-works panel for a bot command, returning
  a ``(caption, InlineKeyboardMarkup)`` pair.

The settings experience (hub → section → field editor, with live previews and
human-friendly copy) lives in :mod:`kurosoden.shared.settings_ui`, which wires
directly onto the real :class:`~nekofetch.services.settings_service.SettingsService`.

Callers wire the result into :class:`nekofetch.ui.screens.Screen`::

    caption, keyboard = tool_screen("levi", "📋 Tasks", "View active tasks", [...])
    await send_screen(client, chat_id,
                      Screen(caption=caption, image=pick_artwork("levi"),
                             keyboard=keyboard),
                      old_msg=...)

Every screen carries the bot's recurring character art via
:func:`nekofetch.ui.artwork.pick_artwork`. HTML parse-mode, bold-led labels,
blockquote dividers, character-icon header — consistent with NekoFetch's
grammar.
"""

from __future__ import annotations

import html
from typing import Sequence

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ── internal helpers ─────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def _icon_for(bot: str) -> str:
    return {
        "lelouch": "🎭",
        "levi": "⚔️",
        "senku": "🧪",
        "gojo": "🔮",
    }.get(bot, "🤖")


def _back(bot: str, target: str, *, label: str = "⇐ Back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"{bot}|{target}")]]
    )


# ── tool screen ──────────────────────────────────────────────────────────────

def tool_screen(
    bot: str,
    title: str,
    kicker: str,
    lines: Sequence[str],
    *,
    back: str = "home",
    back_label: str = "⇐ Back",
) -> tuple[str, InlineKeyboardMarkup]:
    """Build the (caption, keyboard) pair for a *tool* panel.

    Layout::

        🎭  <b>Tasks</b>
        <i>View active and pending tasks</i>

        <body line 1>
        <body line 2>
        <body line 3>

    Use ``lines`` as paragraph-shaped strings — each becomes its own paragraph
    because the screen wraps the whole caption in HTML paragraphs.
    """
    icon = _icon_for(bot)
    parts = [f"{icon}  <b>{_esc(title)}</b>"]
    if kicker:
        parts.append(f"<i>{_esc(kicker)}</i>")
    parts.append("")
    parts.extend(lines)
    caption = "\n".join(parts)
    return caption, _back(bot, back, label=back_label)
