"""Pure render builders for the thumbnail control center channel.

Every function takes already-fetched plain data and returns an HTML string —
no Telegram I/O, no DB access. All copy, emoji, and style tags come from the
centralized message catalog so a single ``en.json`` edit restyles everything.

Matches the same design language as ``log_sections.py`` — bold/italic HTML,
semantic emoji, divider rules, and blockquotes for expandable content.
"""

from __future__ import annotations

import html

from nekofetch.core.constants import RULE_HEAVY
from nekofetch.localization.messages import M, t


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def _header(title: str, ts: str | None = None) -> str:
    """Section header: title, underline rule, optional timestamp."""
    head = f"{title}\n<i>{RULE_HEAVY}</i>"
    if ts:
        head += f"\n{t(M.THUMB_UPDATED, ts=_esc(ts))}"
    return head


# ── Pinned queue overview ──────────────────────────────────────────────────


def queue_section(entries: list[dict], ts: str) -> str:
    """Pinned message listing all franchises needing banners.

    Each entry dict::
        {"anime_title": str, "anime_doc_id": str,
         "total_entries": int, "completed_entries": int}
    """
    if not entries:
        body = t(M.THUMB_QUEUE_EMPTY)
    else:
        rows: list[str] = []
        for e in entries:
            total = e.get("total_entries", 0)
            done = e.get("completed_entries", 0)
            pct = int((done / total * 100)) if total > 0 else 0
            status_glyph = "✅" if done >= total else "🔄"
            rows.append(
                t(M.THUMB_QUEUE_ROW,
                  glyph=status_glyph,
                  title=_esc(e.get("anime_title", "—")),
                  done=done, total=total, pct=pct)
            )
        body = "\n".join(rows)
    return f"{_header(t(M.THUMB_QUEUE_TITLE), ts)}\n\n{body}"


# ── Per-franchise workflow message ─────────────────────────────────────────


def franchise_workflow(
    anime_title: str,
    entries: list[dict],
    selected: dict | None = None,
    ts: str | None = None,
) -> str:
    """Single evolving message for a franchise's thumbnail workflow.

    ``entries`` list with:
        {"index": int, "label": str, "format": str, "status": str,
         "logo_url": str|None, "poster_url": str|None, "bg_url": str|None,
         "thumbnail_url": str|None}
    """
    intro = t(M.THUMB_FRANCHISE_INTRO, title=_esc(anime_title))
    if ts:
        intro += f"\n<i>{_esc(ts)}</i>"

    entry_lines: list[str] = []
    for e in entries:
        glyph = {
            "done": "✅", "ready": "🖼️", "generating": "⚙️",
            "pending": "⏳", "select_logo": "🎨", "select_poster": "📰",
            "select_bg": "🌄",
        }.get(e.get("status", "pending"), "⏳")
        name = _esc(e.get("label", f"Entry {e.get('index', '?')}"))
        entry_lines.append(t(M.THUMB_ENTRY_ROW, glyph=glyph, label=name))

    entry_block = "\n".join(entry_lines)
    return (
        f"{_header(t(M.THUMB_FRANCHISE_TITLE, title=_esc(anime_title)))}\n\n"
        f"{intro}\n\n{entry_block}"
    )


def entry_workflow_detail(
    anime_title: str, entry: dict,
    selected_assets: dict | None = None,
) -> str:
    """Detail panel for one entry being worked on."""
    label = _esc(entry.get("label", f"Entry {entry.get('index', '?')}"))
    logo_url = (selected_assets or {}).get("logo_url")
    poster_url = (selected_assets or {}).get("poster_url")
    bg_url = (selected_assets or {}).get("bg_url")

    asset_lines: list[str] = [
        f"  {'✅' if logo_url else '⬜'} <b>Logo:</b> "
        f"{'Selected' if logo_url else t(M.THUMB_PICK_LOGO)}",
        f"  {'✅' if poster_url else '⬜'} <b>Poster:</b> "
        f"{'Selected' if poster_url else t(M.THUMB_PICK_POSTER)}",
        f"  {'✅' if bg_url else '⬜'} <b>Background:</b> "
        f"{'Selected' if bg_url else t(M.THUMB_PICK_BG)}",
    ]
    return (
        f"<b>{_esc(anime_title)}</b> — <i>{_esc(label)}</i>\n"
        f"<i>{RULE_HEAVY}</i>\n\n{chr(10).join(asset_lines)}"
    )


def telegraph_gallery_teaser(
    title: str, gallery_url: str, asset_type: str, count: int,
) -> str:
    """Short teaser message sent alongside the Telegraph gallery button."""
    type_label = {"logo": "Logo", "poster": "Poster", "backdrop": "Background"}.get(asset_type, "Asset")
    return t(M.THUMB_GALLERY_TEASER,
             type=type_label, count=count, title=_esc(title))
