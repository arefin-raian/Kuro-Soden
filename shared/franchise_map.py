"""Franchise map rendering — a compact, tree-like watch-order view for Senku.

The distribution wizard shows the admin the whole franchise up front so they know
what they're about to build. Telegram has a hard visual width on phones, so a long
season title in a tree will wrap and shatter the alignment. This module renders the
:class:`~kurosoden.shared.distribution_cache.EntryData` list as a tidy tree with
**shortened** labels (season/part or a truncated title), canonical entries only.

Two renderers:

    render_tree(entries, title)  — the HTML tree shown on the franchise-map card.
    render_watch_order(entries)  — a numbered watch-order list for the confirm step.

Both take the already-canonical, already-ordered ``EntryData`` list from the cache,
so ordering and inclusion decisions live in one place (``FranchiseFlowService``),
not here.
"""

from __future__ import annotations

import html

from kurosoden.shared.distribution_cache import EntryData

# Keep a label inside a phone's line width so the tree never wraps. Titles longer
# than this are truncated with an ellipsis; the season/part prefix is preserved.
_MAX_LABEL = 34

_KIND_ICON = {
    "season": "📺",
    "movie": "🎬",
    "special": "✨",
    "ova": "💿",
    "ona": "🌐",
}


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _shorten(label: str, limit: int = _MAX_LABEL) -> str:
    """Trim a label to ``limit`` chars on a word boundary where possible."""
    label = (label or "").strip()
    if len(label) <= limit:
        return label
    cut = label[: limit - 1]
    # Prefer breaking at the last space so we don't slice a word in half.
    if " " in cut[limit // 2:]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"


def _short_entry_label(entry: EntryData) -> str:
    """A tree-safe label: prefix by kind, drop the long ' — Title' tail for seasons.

    ``FranchiseFlowService.entry_label`` appends ' — <full title>' for seasons,
    which is exactly what overflows the tree. For the map we keep the structural
    part (Season N / Part M, or the movie/OVA name) and shorten aggressively.
    """
    kind = (entry.kind or "season").lower()
    if kind == "season":
        base = f"Season {entry.season_number}"
        if entry.season_part:
            base += f" Part {entry.season_part}"
        if entry.episodes:
            base += f"  ·  {entry.episodes} ep"
        return _shorten(base)
    # Movie / OVA / special: the title IS the identity, so keep it (shortened).
    name = entry.title or entry.label or kind.title()
    return _shorten(f"{kind.title()}: {name}") if entry.title else _shorten(name)


def render_tree(entries: list[EntryData], title: str) -> str:
    """Render the franchise as an HTML tree inside a blockquote.

    Uses light box-drawing so it reads as a structure without a monospace block
    (which Telegram renders in a tiny font on mobile). Icons cue the entry kind.
    """
    root = _shorten(title or "Franchise", limit=40)
    lines = [f"<b>{_esc(root)}</b>"]

    total = len(entries)
    for i, entry in enumerate(entries):
        connector = "┗" if i == total - 1 else "┣"
        icon = _KIND_ICON.get((entry.kind or "season").lower(), "📺")
        label = _short_entry_label(entry)
        lines.append(f"{connector} {icon} {_esc(label)}")

    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


def render_watch_order(entries: list[EntryData]) -> str:
    """Render a numbered watch-order list for the confirm step.

    Numbers make the sequence explicit (this is the ordering the admin is
    signing off on), and the full label is kept — this card isn't a tree, so a
    little extra width is fine.
    """
    if not entries:
        return "<i>No entries mapped.</i>"

    lines: list[str] = []
    for i, entry in enumerate(entries, start=1):
        icon = _KIND_ICON.get((entry.kind or "season").lower(), "📺")
        label = entry.label or _short_entry_label(entry)
        lines.append(f"<b>{i}.</b> {icon} {_esc(label)}")
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


def render_copy_block(entries: list[EntryData]) -> str:
    """A plain, copyable watch-order block for the edit step (Markdown/HTML source).

    Mirrors ``FranchiseFlowService.format_mapping_code_block`` line shape so an
    admin who edits and sends it back parses cleanly through
    ``parse_mapping_correction``.
    """
    lines: list[str] = []
    for entry in entries:
        kind = (entry.kind or "season").lower()
        if kind == "season":
            label = f"Season {entry.season_number}"
            if entry.season_part:
                label += f" Part {entry.season_part}"
            ep = f" ({entry.episodes} eps)" if entry.episodes else ""
            src = entry.title[:60] if entry.title else ""
            lines.append(f"{src} → {label}{ep}" if src else f"{label}{ep}")
        else:
            title_part = f": {entry.title[:60]}" if entry.title else ""
            ep = f" ({entry.episodes} ep)" if entry.episodes else ""
            lines.append(f"{kind.title()}{title_part}{ep}")
    return "\n".join(lines)
