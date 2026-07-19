"""Tests for kurosoden/shared/menu_router.py — the shared tool/help panels.

``menu_router`` now owns only :func:`tool_screen` (the how-it-works panels on
each bot's inline buttons). The settings UX moved to
:mod:`kurosoden.shared.settings_ui`; its escaping/preview contract is guarded in
``tests/test_settings_ui.py``.

This guards the escaping contract ``tool_screen`` still depends on: the title and
kicker are literal text and get escaped, while the body ``lines`` are authored
HTML and MUST render verbatim (or the tags show as literal ``<b>`` text).
"""

from __future__ import annotations

from kurosoden.shared.menu_router import tool_screen


def test_tool_screen_lines_render_verbatim():
    caption, _kb = tool_screen(
        "lelouch", "Tasks", "Active work",
        ["A <b>bold</b> line.", "A <code>coded</code> line."],
    )
    assert "<b>bold</b>" in caption
    assert "<code>coded</code>" in caption
    assert "&lt;b&gt;" not in caption


def test_tool_screen_title_is_escaped():
    # The title is a literal label, not authored HTML — a stray angle bracket
    # must not become a tag.
    caption, _kb = tool_screen(
        "levi", "Tasks <beta>", "kicker",
        ["body line"],
    )
    assert "Tasks &lt;beta&gt;" in caption


def test_tool_screen_back_button_targets_bot():
    _caption, kb = tool_screen(
        "senku", "Create", "kicker", ["line"], back="home",
    )
    assert kb.inline_keyboard[-1][0].callback_data == "senku|home"
