"""Levi's native settings panel — config-driven, self-documenting.

The old Levi ``/settings`` was static text pointing at ``/dlset`` / ``/procset``
commands that no handler ever parsed — dead ends. This replaces it with the
*real* settings machinery: it introspects the live ``AppConfig`` through
:class:`SettingsService` (booleans → toggles, lists → comma editors, scalars/
templates → edit prompts) and renders each edit prompt from
:mod:`nekofetch.core.settings_schema`, so every field explains what it does, its
valid values, template variables, an example, and its current value.

Scoped to the sections a downloader actually owns (downloads, acquisition,
processing, rename, metadata, thumbnail, watermark, branding), under the
``levi|set`` callback namespace so it never collides with the admin bot's
``settings|`` panel or Levi's ``levi|`` menu. Edit input runs in ``group=5``
(same slot the admin panel uses) so it doesn't fight Levi's other message
handlers.

Live-toggle rule honoured: a boolean toggle edits the keyboard in place via
``edit_markup`` (no card resend); section navigation and the post-edit
confirmation change the caption/image and so use ``send_screen``.
"""

from __future__ import annotations

import html

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.settings_schema import doc_for, is_owner_only
from nekofetch.domain.enums import Permission
from nekofetch.services.auth_service import AuthService
from nekofetch.services.settings_service import SettingsService
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.components import cb, edit_markup, keyboard
from nekofetch.ui.screens import Screen, send_screen

# Sections a downloader operator owns. Each maps to a real ``AppConfig``
# attribute (dropped silently if absent) and is fully documented in
# settings_schema.py.
LEVI_SECTIONS = (
    "downloads", "acquisition", "processing",
    "rename", "metadata", "thumbnail", "watermark", "branding",
)

# Friendly section titles (the localizer's M.SETTINGS_SECTIONS keys are terse
# slugs; Levi's panel gets its own plain labels so it reads without the catalog).
_SECTION_LABEL = {
    "downloads": "⬇️ Downloads",
    "acquisition": "🎯 Acquisition",
    "processing": "⚙️ Processing",
    "rename": "✎ Rename Templates",
    "metadata": "🏷 Metadata",
    "thumbnail": "🖼 Thumbnail",
    "watermark": "💧 Watermark",
    "branding": "✦ Branding",
}

STATE_EDIT = "levi_settings:edit"


def _label(field: str) -> str:
    return field.replace("_", " ").title()


def _shown(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value)) or "—"
    s = str(value) if value not in (None, "") else "—"
    return s if len(s) <= 18 else s[:17] + "…"


def _edit_prompt(section: str, field: str, current: object, kind: str) -> str:
    """Self-documenting edit prompt built from the settings schema: what it does,
    valid values, template variables (explained), an example, current value."""
    doc = doc_for(section, field)
    lines = [f"<b>✎ {_label(field)}</b>", "<i>─────────────</i>"]
    desc = doc.desc if doc else f"Sets the value of “{_label(field)}”."
    lines.append(f"\n{desc}")
    if doc and doc.option_notes:
        lines.append("\n<b>Options</b>")
        lines += [f"• <code>{html.escape(val)}</code> — {note}"
                  for val, note in doc.option_notes.items()]
    elif doc and doc.options:
        lines.append("\n<b>Valid:</b> " + " · ".join(doc.options))
    if doc and doc.placeholders:
        lines.append("\n<b>Variables</b>")
        lines += [f"• <code>{html.escape(var)}</code> — {expl}"
                  for var, expl in doc.placeholders.items()]
    if doc and doc.html:
        lines.append("\n<i>HTML is allowed in this value.</i>")
    if doc and doc.example:
        lines.append(f"\n<b>Example:</b> <code>{html.escape(doc.example)}</code>")
    shown = ", ".join(map(str, current)) if isinstance(current, list) else str(current)
    lines.append(f"\n<b>Current:</b> <code>{html.escape(shown or '—')}</code>")
    lines.append(
        "\n<i>Send the new value as a message"
        + (" (comma-separated for a list)." if kind == "list" else ".")
        + "</i>"
    )
    return "\n".join(lines)


def _section_rows(svc: SettingsService, section: str) -> list[list[tuple[str, str]]]:
    """Build the (label, callback) rows for one section's fields."""
    rows: list[list[tuple[str, str]]] = []
    for field, value, kind in svc.section_fields(section):
        label = _label(field)
        if kind == "bool":
            mark = "🟢" if value else "⚪️"
            rows.append([(f"{mark}  {label}", cb("levi", "set", "tog", f"{section}.{field}"))])
        else:
            rows.append([(f"{label}:  {_shown(value)}",
                          cb("levi", "set", "edit", f"{section}.{field}"))])
    rows.append([("⇐ Back", cb("levi", "set", "home"))])
    return rows


def build_home_screen(container: Container) -> Screen:
    """The settings section-list screen. Module-level so both the ``/settings``
    command and the ``levi|set|home`` callback render the identical screen."""
    svc = SettingsService(container)
    sections = [s for s in LEVI_SECTIONS if svc.section(s) is not None]
    rows: list[list[tuple[str, str]]] = []
    for i in range(0, len(sections), 2):
        rows.append([(_SECTION_LABEL[s], cb("levi", "set", "sec", s))
                     for s in sections[i:i + 2]])
    rows.append([("⇐ Home", cb("levi", "home"))])
    return Screen(
        caption=(
            "<b>⚔️ Levi — Downloader Settings</b>\n\n"
            "Everything the download detail runs on. Concurrency and quality, "
            "the rename templates, branding, watermark, metadata. Tap a "
            "section. Toggles flip in place; text fields open a prompt that "
            "explains itself.\n\n"
            "<i>Change takes effect on the next job pickup.</i>"
        ),
        image=pick_artwork("levi"),
        keyboard=keyboard(*rows),
    )


def register(client: Client, container: Container) -> None:
    """Wire Levi's native settings panel under ``levi|set``."""
    auth = AuthService(container)
    fsm = FSM(container.redis, bot="levi")
    svc = SettingsService(container)

    def _allowed(q: CallbackQuery) -> bool:
        user = getattr(q, "nf_user", None)
        return bool(user and auth.has_permission(user, Permission.CONFIGURE))

    async def _deny(q: CallbackQuery, section: str) -> bool:
        """True (and answers) if the user may not touch this section."""
        if not _allowed(q):
            await q.answer("You don't have permission to configure Levi.", show_alert=True)
            return True
        if is_owner_only(section) and not auth.is_owner(getattr(q, "nf_user", None)):
            await q.answer("That section is owner-only.", show_alert=True)
            return True
        return False

    def _home_screen() -> Screen:
        return build_home_screen(container)

    async def _render_section(q: CallbackQuery, section: str) -> None:
        caption = (
            f"<b>{_SECTION_LABEL.get(section, section.title())}</b>\n\n"
            "🟢 = on · ⚪️ = off. Tap a text field to edit it — the prompt shows "
            "valid values, variables, and an example."
        )
        screen = Screen(caption=caption, image=pick_artwork("levi"),
                        keyboard=keyboard(*_section_rows(svc, section)))
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)

    # ── Settings home (section list) ────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^levi\|set\|home$"))
    async def _home(_: Client, q: CallbackQuery) -> None:
        if not _allowed(q):
            await q.answer("You don't have permission to configure Levi.", show_alert=True)
            return
        await q.answer()
        await send_screen(client, q.message.chat.id, _home_screen(), old_msg=q.message)

    # ── One section ─────────────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^levi\|set\|sec\|"))
    async def _section(_: Client, q: CallbackQuery) -> None:
        section = q.data.split("|", 3)[3]
        if await _deny(q, section):
            return
        await q.answer()
        await _render_section(q, section)

    # ── Toggle a boolean (live keyboard edit, no resend) ────────────────────
    @client.on_callback_query(filters.regex(r"^levi\|set\|tog\|"))
    async def _toggle(_: Client, q: CallbackQuery) -> None:
        key = q.data.split("|", 3)[3]
        section, field = key.split(".", 1)
        if await _deny(q, section):
            return
        new_val = await svc.toggle(section, field)
        await q.answer(f"{_label(field)} → {'on' if new_val else 'off'}")
        # Keyboard-only change → edit in place rather than resending the card.
        await edit_markup(q, _section_rows(svc, section))

    # ── Edit a scalar/list/template ─────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^levi\|set\|edit\|"))
    async def _edit(_: Client, q: CallbackQuery) -> None:
        key = q.data.split("|", 3)[3]
        section, field = key.split(".", 1)
        if await _deny(q, section):
            return
        current = getattr(svc.section(section), field, "")
        kind = "list" if isinstance(current, list) else "value"
        await fsm.set(q.from_user.id, STATE_EDIT, section=section, field=field)
        await q.answer()
        await q.message.reply(
            _edit_prompt(section, field, current, kind),
            reply_markup=keyboard([("✗ Cancel", cb("levi", "set", "sec", section))]),
            parse_mode=ParseMode.HTML,
        )

    @client.on_message(filters.text & filters.private & ~filters.command(["start"]), group=5)
    async def _edit_input(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, data = await fsm.get(message.from_user.id)
        if state != STATE_EDIT:
            return
        user = getattr(message, "nf_user", None)
        if not (user and auth.has_permission(user, Permission.CONFIGURE)):
            return
        section, field = data.get("section"), data.get("field")
        if is_owner_only(section) and not auth.is_owner(user):
            await fsm.clear(message.from_user.id)
            await message.reply("That section is owner-only.", parse_mode=ParseMode.HTML)
            return
        await fsm.clear(message.from_user.id)
        try:
            value = await svc.set_typed(section, field, message.text)
        except (ValueError, KeyError, TypeError):
            await message.reply(
                "That value didn't parse. Check the type and try again.",
                parse_mode=ParseMode.HTML,
            )
            return
        shown = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        await message.reply(
            f"<b>✓ {_label(field)}</b> set to <code>{html.escape(shown)}</code>.",
            reply_markup=keyboard([("⇐ Back", cb("levi", "set", "sec", section))]),
            parse_mode=ParseMode.HTML,
        )
