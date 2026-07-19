"""Shared menu router helpers for all four Kuro Soden pipeline bots.

Built so every key-press on an inline button produces a beautiful, helpful
screen instead of the previous "Type /X in chat" dead toast. Three
primitives, each returning a ``(caption, InlineKeyboardMarkup)`` pair:

* :func:`tool_screen`         — usage / how-it-works panel for a bot command.
* :func:`settings_hub`        — the per-bot settings root with sub-menu rows.
* :func:`settings_onboarding` — rich help panel for a single settings key,
  modeled after NekoFetch's own edit-prompt (bold "About", blockquote
  description, options, placeholders, example, danger note, current value,
  edit hint). Each piece is conditionally rendered so the screen never has
  empty section headers.

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


# ── settings hub ─────────────────────────────────────────────────────────────

def settings_hub(
    bot: str,
    title: str,
    body: str,
    items: Sequence[tuple[str, str]],
    *,
    back: str = "home",
    back_label: str = "⇐ Back",
) -> tuple[str, InlineKeyboardMarkup]:
    """Build the (caption, keyboard) pair for the bot's settings root.

    ``items`` is a sequence of ``(label, key)`` pairs; each becomes an inline
    button whose ``callback_data`` is ``{bot}|set|{key}``. Lines are emitted
    pairwise (2 buttons per row) so the keyboard never stretches vertically.
    """
    # ``body`` is developer-authored HTML (it carries <i>/<b> emphasis), so it is
    # emitted verbatim — escaping it would turn the tags into literal text.
    icon = _icon_for(bot)
    caption = (
        f"{icon}  <b>{_esc(title)}</b>\n\n"
        f"{body}"
    )
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, (label, key) in enumerate(items):
        row.append(InlineKeyboardButton(
            label, callback_data=f"{bot}|set|{key}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(back_label, callback_data=f"{bot}|{back}")])
    return caption, InlineKeyboardMarkup(buttons)


# ── settings onboarding ──────────────────────────────────────────────────────

def settings_onboarding(
    bot: str,
    key: str,
    title: str,
    about: str,
    *,
    when_to_use: str = "",
    options: Sequence[tuple[str, str]] | None = None,
    placeholders: Sequence[tuple[str, str]] | None = None,
    supports_html: bool = False,
    example: str = "",
    current: str = "",
    danger: str = "",
    hint: str = "Send the new value as a chat message — I'll apply it.",
    back: str = "settings",
    back_label: str = "⇐ Back to Settings",
) -> tuple[str, InlineKeyboardMarkup]:
    """Build the (caption, keyboard) pair for one settings key's help panel.

    Sections rendered (each only when supplied):
      • <b>Title</b>            — always
      • <i>About</i>            — always, in a blockquote
      • <b>When to use…</b>    — when ``when_to_use`` set
      • <b>Options</b>          — when ``options`` set      (val : desc)
      • <b>Placeholders</b>     — when ``placeholders`` set (var : desc)
      • <b>HTML allowed</b>     — when ``supports_html`` True
      • <b>Example</b>          — when ``example`` set, in a blockquote
      • <b>Current</b>          — when ``current`` set
      • <b>Danger</b>           — when ``danger`` set, in italics
      • <i>Hint</i>             — always, tells the user how to apply the value

    Modeled after NekoFetch's :func:`nekofetch.bots.admin.handlers.settings
    ._edit_prompt`, so admins already familiar with that UI feel at home.
    """
    # Escaping rule (mirrors NekoFetch's ``_edit_prompt``): prose fields
    # (about / when_to_use / option & placeholder *descriptions* / danger / hint)
    # are authored WITH HTML by the caller, so they pass through verbatim. Only
    # literal *values* the user might type — option keys, placeholder tokens, the
    # example template, the current value — are escaped, so a template such as
    # ``<b>{title}</b>`` shows as literal text rather than rendering.
    icon = _icon_for(bot)
    parts: list[str] = [f"{icon}  <b>{_esc(title)}</b>", ""]
    parts.append(f"<blockquote expandable><i>About:</i> {about}</blockquote>")
    if when_to_use:
        parts += ["", f"<b>When to change:</b> {when_to_use}"]
    if options:
        parts += ["", "<b>Options :</b>"]
        for val, desc in options:
            parts.append(
                f"  <code>{_esc(val)}</code> — {desc}"
            )
    if placeholders:
        parts += ["", "<b>Placeholders you can use :</b>"]
        for var, desc in placeholders:
            parts.append(
                f"  <code>{_esc(var)}</code> — {desc}"
            )
    if supports_html:
        parts += ["", "🏷  <i>HTML (bold/italic/code/blockquote) is allowed in this field.</i>"]
    if example:
        parts += ["",
                  f"💡 <b>Example:</b>",
                  f"<blockquote expandable><code>{_esc(example)}</code></blockquote>"]
    if current:
        parts += ["", f"📌 <b>Current :</b> <code>{_esc(current)}</code>"]
    if danger:
        parts += ["",
                  f"⚠️ <i>Danger :</i> {danger}"]
    parts += ["", f"<i>{hint}</i>"]

    # Tiny correlation header — confirms the user pressed the right key.
    parts += ["", f"<i>key :</i> <code>{_esc(key)}</code>"]

    caption = "\n".join(parts)
    return caption, _back(bot, back, label=back_label)
