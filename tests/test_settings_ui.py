"""Tests for kurosoden/shared/settings_ui.py — the human-friendly settings engine.

Covers the two pure, high-value pieces that the whole UX rests on:

  * ``parse_user_markup`` — accept whatever a normal person sends (Telegram-native
    bold/italic, hand-typed HTML, Markdown) and preserve real line breaks, turning
    a typed literal ``\\n`` into a real newline.
  * ``render_sample`` — fill a template with realistic sample data so the editor
    can PREVIEW how a card will look instead of showing bare ``{tokens}``.

Plus the label helpers and screen builders (no raw slugs, preview present).
"""

from __future__ import annotations

from types import SimpleNamespace

from kurosoden.shared.settings_ui import (
    field_label,
    field_screen,
    hub_screen,
    parse_user_markup,
    render_sample,
    section_label,
)


# ── a tiny fake Message good enough for parse_user_markup ────────────────────

def _msg(text, *, entities=None, html=None):
    """Build a stand-in Message.

    ``html`` is what Pyrogram's ``message.text.html`` would return; we model the
    Str subclass with a plain object that exposes a ``.html`` attribute.
    """
    class _Str(str):
        pass

    s = _Str(text)
    if html is not None:
        s.html = html  # type: ignore[attr-defined]
    return SimpleNamespace(text=s, caption=None, entities=entities,
                           caption_entities=None)


# ── parse_user_markup ────────────────────────────────────────────────────────

def test_hand_typed_html_is_kept():
    out = parse_user_markup(_msg("<b>{title}</b> is here"))
    assert out == "<b>{title}</b> is here"


def test_native_telegram_styling_uses_html_rendering():
    # Entities present → we take the message's .html rendering.
    out = parse_user_markup(_msg(
        "bold here",
        entities=[object()],
        html="<b>bold</b> here",
    ))
    assert out == "<b>bold</b> here"


def test_markdown_bold_and_italic_convert():
    out = parse_user_markup(_msg("**big** and _small_"))
    assert "<b>big</b>" in out
    assert "<i>small</i>" in out


def test_markdown_code_becomes_code_span():
    out = parse_user_markup(_msg("set it to `480p` please"))
    # A backtick span becomes a <code> span; the rest is left as prose.
    assert "<code>480p</code>" in out


def test_markdown_code_content_is_escaped():
    # Ampersands/brackets INSIDE a code span are escaped so they stay literal.
    # (The span marker itself is markdown, so this doesn't look like hand HTML.)
    out = parse_user_markup(_msg("literal `a & b` value"))
    assert "<code>a &amp; b</code>" in out


def test_literal_backslash_n_becomes_real_newline():
    out = parse_user_markup(_msg("line one\\nline two"))
    assert out == "line one\nline two"


def test_real_newlines_are_preserved():
    out = parse_user_markup(_msg("line one\nline two"))
    assert out == "line one\nline two"


def test_plain_text_passes_through():
    out = parse_user_markup(_msg("just words, no markup"))
    assert out == "just words, no markup"


def test_markdown_link_converts():
    out = parse_user_markup(_msg("[join](https://t.me/x)"))
    assert '<a href="https://t.me/x">join</a>' in out


# ── render_sample ────────────────────────────────────────────────────────────

def test_render_sample_fills_known_tokens():
    out = render_sample("<b>{title}</b> — {episodes} eps")
    assert "Attack on Titan" in out
    assert "{title}" not in out
    assert "25" in out


def test_render_sample_keeps_unknown_tokens_visible():
    out = render_sample("{definitely_not_a_token}")
    # Unknown tokens stay so a typo is visible rather than silently blanked.
    assert "{definitely_not_a_token}" in out


def test_render_sample_normalises_literal_newline():
    out = render_sample("{title}\\n{episodes}")
    assert "\n" in out
    assert "\\n" not in out


# ── labels never leak raw slugs ──────────────────────────────────────────────

def test_field_label_is_human():
    assert field_label("concurrent_downloads") == "Downloads at Once"
    # Unknown slug still gets title-cased, never shown raw with underscores.
    assert field_label("some_new_field") == "Some New Field"


def test_section_label_is_human():
    assert section_label("post_format") == "🎨 How Posts Look"


# ── screen builders ──────────────────────────────────────────────────────────

def test_hub_screen_lists_sections_with_friendly_labels():
    screen = hub_screen("senku", "Senku Settings", "Blurb here.",
                        ["post_format", "bot"])
    # Buttons carry friendly labels, callbacks use the {bot}|set|sec|{section} shape.
    flat = [b for row in screen.keyboard.inline_keyboard for b in row]
    labels = [b.text for b in flat]
    assert "🎨 How Posts Look" in labels
    datas = [b.callback_data for b in flat]
    assert "senku|set|sec|post_format" in datas


def test_field_screen_shows_live_preview_for_templates():
    # A template field (has placeholders in the schema) renders a filled preview.
    screen = field_screen("senku", "post_format", "movie_card_template", "", "value")
    assert "Preview" in screen.caption
    # The preview is filled with real sample data (the token list further down
    # still shows {title} as a documented variable — that's expected).
    preview = screen.caption.split("Preview")[1].split("You can drop in")[0]
    assert "{title}" not in preview
    assert "Attack on Titan" in screen.caption


def test_field_screen_has_no_raw_slug():
    screen = field_screen("senku", "post_format", "buttons_per_row", 2, "value")
    # The human label shows, never the underscore slug.
    assert "Buttons per Row" in screen.caption
    assert "buttons_per_row" not in screen.caption
