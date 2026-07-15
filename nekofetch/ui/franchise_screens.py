"""Franchise Flow screens — franchise mapping, source scan, post-processing confirmation.

These screens are part of the new franchise-structure-first pipeline. They are
standalone builders (no Telegram I/O) that produce Screen objects for the
admin bot handlers to send/render.

Works alongside ``FranchiseFlowService`` to provide the visual interface for:
  - Franchise mapping with include/exclude per entry
  - Source availability scan reports
  - Post-processing mapping confirmation
  - Editing mechanism via message replies
"""

from __future__ import annotations

import html
from pathlib import Path

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from nekofetch.core.constants import BULLET
from nekofetch.localization.messages import M, t
from nekofetch.services.franchise_flow import FranchiseFlowService, FranchiseMapping
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import CAPTION_LIMIT, PARSE_MODE, Screen, _truncate_html


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


# ── Franchise Mapping Selection Screen ──────────────────────────────────────


def franchise_map_selection(
    mapping: FranchiseMapping,
    backdrop_url: str | None = None,
) -> Screen:
    """Show the franchise structure with include/exclude toggles.

    Each entry has a corresponding button that toggles its inclusion.
    Staff can also select "All" or confirm their selection.
    """
    lines: list[str] = []
    lines.append(f"<b>📋 Select Franchise Components</b>")
    lines.append("")
    lines.append("Choose which entries to include for this request:")
    lines.append("")

    included_count = mapping.included_count
    for entry in mapping.entries:
        label = FranchiseFlowService.entry_label(entry)
        prefix = "✅" if entry.included else "☐"
        ep_str = f" ({entry.episodes} ep)" if entry.episodes else ""
        # label already includes season part via entry_label, so no separate part_str needed
        lines.append(f"{prefix}  <b>{_esc(label)}</b>{ep_str}")

    lines.append("")
    lines.append(f"<i>{included_count}/{mapping.entry_count} entries selected</i>")

    caption = _truncate_html("\n".join(lines), CAPTION_LIMIT)

    # Build toggle buttons — one per entry
    kb_rows: list[list[InlineKeyboardButton]] = []
    for entry in mapping.entries:
        label = FranchiseFlowService.entry_label(entry)
        prefix = "✅" if entry.included else "☐"
        short_label = f"{prefix} {label[:36]}"
        entry_key = FranchiseFlowService._entry_key(entry)
        kb_rows.append([
            InlineKeyboardButton(short_label, callback_data=cb("franchise", "toggle", entry_key)),
        ])

    # Control buttons
    kb_rows.append([
        InlineKeyboardButton(t(M.MANUAL_WIZ_COMP_ENTIRE), callback_data=cb("franchise", "all")),
        InlineKeyboardButton("Confirm ✓", callback_data=cb("franchise", "confirm")),
    ])
    kb_rows.append([
        InlineKeyboardButton(t(M.BTN_BACK), callback_data=cb("staff", "requests", 0)),
    ])

    # Image
    image: str | Path | None = backdrop_url or pick_artwork()

    return Screen(caption=caption, image=image, keyboard=InlineKeyboardMarkup(kb_rows))


def franchise_scan_screen(
    mapping: FranchiseMapping,
    backdrop_url: str | None = None,
) -> Screen:
    """Show the source availability report after scanning."""
    lines: list[str] = []
    lines.append(f"<b>📡 Source Availability Scan</b>")
    lines.append("")
    lines.append("Available sources and their coverage:")
    lines.append("")

    for entry in mapping.included_entries:
        label = FranchiseFlowService.entry_label(entry)
        note = entry.source_note or "pending scan"
        lines.append(f"  {BULLET} <b>{_esc(label)}</b> — {_esc(note)}")

    lines.append("")
    lines.append("<i>Select the best source strategy:</i>")

    kb = keyboard(
        [("Best single source", cb("franchise", "source", "best"))],
        [("Combination of sources", cb("franchise", "source", "combo"))],
        [("Manual source assignment", cb("franchise", "source", "manual"))],
        [(t(M.BTN_BACK), cb("franchise", "back"))],
    )

    image: str | Path | None = backdrop_url or pick_artwork()
    return Screen(caption="\n".join(lines), image=image, keyboard=kb)


# ── Post-Processing Confirmation Screen ─────────────────────────────────────


def post_processing_confirmation(
    mapping: FranchiseMapping,
    code: str,
    backdrop_url: str | None = None,
) -> Screen:
    """Show the mapped structure in a copyable code block for admin confirmation.

    The code block (via ``<pre>``) gives Telegram's copy button. The admin can:
      - Confirm — accept the mapping and publish
      - Edit — enables reply mode; whatever the admin types back becomes a
        direct correction to the mapping (e.g. ``Season 3 Part 1 → 10 eps``)
      - Cancel — abandon the publishing
    """
    lines: list[str] = []
    lines.append(f"<b>📦 Mapping Confirmation — {_esc(mapping.root_title)}</b>")
    lines.append(f"<b>Code:</b> {_esc(code)}")
    lines.append("")
    lines.append("Copy the block below to edit, or use the buttons:")
    lines.append("")

    # Copyable code block — Telegram shows a "copy" button on <pre> blocks
    code_block = FranchiseFlowService.format_mapping_code_block(mapping)
    lines.append(f"<pre>{_esc(code_block)}</pre>")

    lines.append("")
    lines.append("<i>✅ Confirm — publish with this mapping</i>")
    lines.append("<i>✏️ Edit — reply to this message with corrections</i>")
    lines.append("<i>❌ Cancel — abort publishing</i>")

    kb = keyboard([
        ("✅ Confirm & Publish", cb("franchise", "confirm_pub", code)),
        ("✏️  Edit Mapping", cb("franchise", "edit", code)),
        ("❌ Cancel", cb("franchise", "cancel", code)),
    ])

    image: str | Path | None = backdrop_url or pick_artwork()
    return Screen(caption="\n".join(lines), image=image, keyboard=kb)


# ── Edit Success Screen ─────────────────────────────────────────────────────


def edit_acknowledgement(
    result: str,
    backdrop_url: str | None = None,
    code: str | None = None,
) -> Screen:
    """Show that an edit was applied successfully."""
    lines: list[str] = []
    lines.append(f"<b>✅ Edit Applied</b>")
    lines.append("")
    lines.append(result)
    lines.append("")
    lines.append("The mapping has been updated.")

    kb = keyboard([
        (t(M.BTN_BACK), cb("franchise", "refresh", code or "")),
    ])

    image: str | Path | None = backdrop_url or pick_artwork()
    return Screen(caption="\n".join(lines), image=image, keyboard=kb)
