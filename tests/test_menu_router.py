"""Tests for kurosoden/shared/menu_router.py — the shared settings/help panels.

Guards the escaping contract that all four Kuro Sōden bots depend on:

  * developer-authored **prose** (about / when_to_use / option & placeholder
    descriptions / danger / hint / hub body) carries its own HTML emphasis and
    MUST pass through verbatim, or the tags render as literal ``<b>`` text; while
  * literal **values** a user might type (option keys, placeholder tokens, the
    example template, the current value) MUST stay escaped, so a template like
    ``<b>{title}</b>`` shows as text instead of rendering.

This is the exact bug the panels drifted into: prose was being ``html.escape``d,
so admins saw raw ``<code>`` tags in every settings screen.
"""

from __future__ import annotations

from kurosoden.shared.menu_router import (
    settings_hub,
    settings_onboarding,
    tool_screen,
)


def test_onboarding_prose_html_renders_verbatim():
    caption, _kb = settings_onboarding(
        "senku", "branding",
        title="Channel Branding",
        about="Footer under <b>post_format</b>.",
        when_to_use="When the <i>brand</i> changes.",
        hint="Open <b>Settings</b>.",
        danger="<b>channel_id</b> must be valid.",
    )
    # Authored tags survive — not turned into &lt;b&gt;.
    assert "<b>post_format</b>" in caption
    assert "<i>brand</i>" in caption
    assert "<b>Settings</b>" in caption
    assert "<b>channel_id</b>" in caption
    assert "&lt;b&gt;" not in caption


def test_onboarding_values_are_escaped():
    caption, _kb = settings_onboarding(
        "gojo", "caption",
        title="Caption",
        about="The caption template.",
        placeholders=[("{title}", "Anime title.")],
        example="<b>{title}</b>",
        current="<i>live</i>",
    )
    # A user-typeable template shows literally, so its tags don't render.
    assert "&lt;b&gt;{title}&lt;/b&gt;" in caption
    assert "&lt;i&gt;live&lt;/i&gt;" in caption


def test_hub_body_prose_renders_verbatim():
    caption, _kb = settings_hub(
        "levi", title="Levi Settings",
        body="Tune <i>downloads</i> and <b>processing</b>.",
        items=[("Downloads", "downloads")],
    )
    assert "<i>downloads</i>" in caption
    assert "<b>processing</b>" in caption
    assert "&lt;i&gt;" not in caption


def test_tool_screen_lines_render_verbatim():
    caption, _kb = tool_screen(
        "lelouch", "Tasks", "Active work",
        ["A <b>bold</b> line.", "A <code>coded</code> line."],
    )
    assert "<b>bold</b>" in caption
    assert "<code>coded</code>" in caption
    assert "&lt;b&gt;" not in caption
