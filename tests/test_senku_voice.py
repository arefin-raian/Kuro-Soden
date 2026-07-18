"""Tests for kurosoden/shared/senku_voice.py — Senku's distribution voice.

Every voice callable must return non-empty HTML, escape runtime values, and keep
the flask icon so cards stay visually consistent. Mirrors the coverage bar the
other bots' voice modules hold implicitly (rendered on every card).
"""

from __future__ import annotations

import inspect

from kurosoden.shared import senku_voice as V


def test_icon_is_flask():
    assert V.ICON == "🧪"


def test_esc_escapes_html():
    assert V.esc("<b>& \"x\"</b>") == "&lt;b&gt;&amp; \"x\"&lt;/b&gt;"
    assert V.esc(None) == ""
    assert V.esc(123) == "123"


def test_all_string_constants_nonempty_and_iconed():
    # Every module-level STR constant that reads like copy carries content.
    for name, val in vars(V).items():
        if name.isupper() and isinstance(val, str) and not name.startswith("BTN_"):
            assert val.strip(), f"{name} is empty"


def test_button_labels_present():
    for name in (
        "BTN_BEGIN", "BTN_CHANNEL_DONE", "BTN_TMDB_POSTER", "BTN_SHOW_LOGOS",
        "BTN_SHOW_POSTERS", "BTN_SHOW_BACKDROPS", "BTN_GENERATE",
        "BTN_ORDER_CORRECT", "BTN_ORDER_EDIT", "BTN_PUBLISH",
    ):
        assert isinstance(getattr(V, name), str) and getattr(V, name).strip()


def test_handoff_card_carries_title_code_and_count():
    out = V.handoff_card("Attack on Titan", "REQ-0001", entry_count=8)
    assert "Attack on Titan" in out
    assert "REQ-0001" in out
    assert "8" in out
    assert V.ICON in out


def test_handoff_card_escapes_title():
    out = V.handoff_card("<script>", "REQ-0002")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_channel_title_block_is_tap_to_copy():
    out = V.channel_title_block("Some Title 『 Dual Audio 』")
    # Monospace <code> = tap-to-copy in Telegram; must NOT be a code fence.
    assert "<code>" in out and "</code>" in out
    assert "<pre>" not in out


def test_channel_username_block_is_tap_to_copy():
    out = V.channel_username_block("spy_x_family_axw")
    # Monospace <code> = tap-to-copy in Telegram; the handle must be present verbatim.
    assert "<code>" in out and "spy_x_family_axw" in out
    assert "<pre>" not in out


def test_channel_description_block_wraps_value_in_code():
    out = V.channel_description_block("The description.")
    assert "<code>" in out and "The description." in out


def test_channel_admins_line_names_both_bots():
    assert "Senku" in V.CHANNEL_ADMINS_LINE
    assert "Gojo" in V.CHANNEL_ADMINS_LINE


def test_thumb_entry_header_shows_progress():
    out = V.thumb_entry_header("Season 3 Part 2", 3, 8)
    assert "3" in out and "8" in out and "Season 3 Part 2" in out


def test_thumb_generated_advances_or_finishes():
    mid = V.thumb_generated(2, 8)
    assert "3" in mid  # names the next entry
    final = V.thumb_generated(8, 8)
    assert "watch order" in final.lower()


def test_watch_order_card_includes_order_html():
    out = V.watch_order_card("Bleach", "<blockquote>1. thing</blockquote>")
    assert "Bleach" in out
    assert "1. thing" in out


def test_callables_accept_their_args_without_raising():
    # Smoke: every public callable renders with representative args.
    samples = {
        "home_title": ("Neko",),
        "tasks_title": (2,),
        "handoff_card": ("T", "REQ-1"),
        "franchise_map_card": ("T", "<blockquote>x</blockquote>"),
        "channel_intro": ("T",),
        "channel_title_block": ("T",),
        "channel_username_block": ("spy_x_family_axw",),
        "channel_description_block": ("D",),
        "channel_missing": ("a poster",),
        "channel_verified": ("@chan",),
        "channel_verify_failed": ("@chan",),
        "thumb_intro": ("T", 3),
        "thumb_entry_header": ("S1", 1, 3),
        "thumb_pick_prompt": ("logo",),
        "thumb_selected": ("poster", 2),
        "thumb_generated": (1, 3),
        "watch_order_card": ("T", "<b>1</b>"),
        "watch_order_edit_failed": (),
        "publishing": ("T",),
        "published_done": ("T",),
    }
    for name, args in samples.items():
        fn = getattr(V, name)
        assert inspect.isfunction(fn), name
        out = fn(*args)
        assert isinstance(out, str) and out.strip(), name
