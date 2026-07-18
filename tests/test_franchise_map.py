"""Tests for kurosoden/shared/franchise_map.py — tree + watch-order rendering.

Covers the width discipline the spec calls for (long titles must not overflow and
break the tree), canonical-order preservation, kind icons, and the copyable
watch-order block used by the edit step.
"""

from __future__ import annotations

from kurosoden.shared.distribution_cache import EntryData
from kurosoden.shared.franchise_map import (
    _MAX_LABEL,
    render_copy_block,
    render_tree,
    render_watch_order,
)


def _long_franchise():
    return [
        EntryData(index=1, label="Season 1", kind="season", season_number=1,
                  episodes=25, title="A Very Long Root Season Title That Overflows Phones"),
        EntryData(index=2, label="Season 3 Part 2", kind="season",
                  season_number=3, season_part=2),
        EntryData(index=3, label="Movie: Some Extremely Long Movie Subtitle Here Indeed",
                  kind="movie", media_type="movie",
                  title="Some Extremely Long Movie Subtitle Here Indeed"),
        EntryData(index=4, label="OVA: Lost Girls", kind="ova", title="Lost Girls"),
    ]


def test_tree_wraps_in_blockquote_with_root_bold():
    out = render_tree(_long_franchise(), "Attack on Titan")
    assert out.startswith("<blockquote>")
    assert out.endswith("</blockquote>")
    assert "<b>Attack on Titan</b>" in out


def test_tree_no_line_exceeds_width_budget():
    out = render_tree(_long_franchise(), "A Franchise With A Long Name Beyond Budget")
    stripped = out.replace("<blockquote>", "").replace("</blockquote>", "")
    stripped = stripped.replace("<b>", "").replace("</b>", "")
    for line in stripped.split("\n"):
        # Strip the connector + icon prefix; the label itself is width-limited.
        # Allow generous headroom for the prefix/icon; the key is no runaway lines.
        assert len(line) <= _MAX_LABEL + 20, f"line too wide: {line!r}"


def test_tree_last_entry_uses_terminal_connector():
    out = render_tree(_long_franchise(), "T")
    assert "┗" in out  # last child
    assert "┣" in out  # non-last children


def test_tree_shortens_long_labels_with_ellipsis():
    out = render_tree(_long_franchise(), "T")
    assert "…" in out


def test_tree_uses_kind_icons():
    out = render_tree(_long_franchise(), "T")
    assert "📺" in out  # season
    assert "🎬" in out  # movie


def test_watch_order_is_numbered_in_sequence():
    out = render_watch_order(_long_franchise())
    assert "<b>1.</b>" in out
    assert "<b>4.</b>" in out
    # Order preserved: entry 1 appears before entry 4 in the string.
    assert out.index("<b>1.</b>") < out.index("<b>4.</b>")


def test_watch_order_empty():
    assert "No entries" in render_watch_order([])


def test_copy_block_shape_matches_mapping_source():
    out = render_copy_block(_long_franchise())
    lines = out.split("\n")
    assert len(lines) == 4
    # A season WITH a source title carries the ' → Season N' arrow the parser
    # expects; a titleless season falls back to the bare label (mirrors
    # FranchiseFlowService.format_mapping_code_block).
    assert "→ Season 1" in lines[0]
    assert lines[1] == "Season 3 Part 2"
    assert lines[2].startswith("Movie")
    assert lines[3].startswith("Ova")


def test_copy_block_escapes_nothing_by_design():
    # The copy block is a plain-text source for the admin to edit; it is NOT
    # HTML-escaped (it's sent as a copyable code block, parsed back verbatim).
    out = render_copy_block([EntryData(index=1, label="S1", season_number=1,
                                       title="A & B")])
    assert "A & B" in out
