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
    _section_rows,
    field_label,
    field_screen,
    hub_screen,
    list_screen,
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


# ── field allow-list (mount a subset of a shared section) ─────────────────────

class _FakeSvc:
    """Minimal stand-in for SettingsService.section_fields, driven by a dict of
    section → [(field, value, kind), …]."""

    def __init__(self, fields):
        self._fields = fields

    def section_fields(self, name):
        return self._fields.get(name, [])


def _row_datas(rows):
    return [b for row in rows for (_, b) in row]


def test_section_rows_full_shows_every_field():
    svc = _FakeSvc({"security": [
        ("force_subscribe", False, "bool"),
        ("watermarking", False, "bool"),
        ("owner_id", 0, "value"),
    ]})
    rows = _section_rows(svc, "lelouch", "security")
    datas = _row_datas(rows)
    assert any("security.force_subscribe" in d for d in datas)
    assert any("security.watermarking" in d for d in datas)
    assert any("security.owner_id" in d for d in datas)


def test_section_rows_allow_list_hides_unlisted_fields():
    svc = _FakeSvc({"security": [
        ("force_subscribe", False, "bool"),
        ("watermarking", False, "bool"),
        ("owner_id", 0, "value"),
    ]})
    rows = _section_rows(svc, "lelouch", "security", allow=["force_subscribe"])
    datas = _row_datas(rows)
    assert any("security.force_subscribe" in d for d in datas)
    # Unlisted fields must not appear at all.
    assert not any("security.watermarking" in d for d in datas)
    assert not any("security.owner_id" in d for d in datas)


def test_section_rows_allow_list_preserves_given_order():
    svc = _FakeSvc({"queue": [
        ("max_visible", 10, "value"),
        ("position_recalc_seconds", 5, "value"),
    ]})
    rows = _section_rows(svc, "lelouch", "queue",
                         allow=["position_recalc_seconds", "max_visible"])
    datas = [d for d in _row_datas(rows) if d.startswith("lelouch|set")]
    # First data row should be the first allow-list entry.
    assert "queue.position_recalc_seconds" in datas[0]
    assert "queue.max_visible" in datas[1]


def test_section_rows_list_field_opens_list_manager():
    svc = _FakeSvc({"security": [
        ("force_subscribe_channels", [-100123], "list"),
    ]})
    rows = _section_rows(svc, "lelouch", "security")
    datas = _row_datas(rows)
    # A list-typed field routes to the list manager (set|list), NOT the edit card.
    assert any(d == "lelouch|set|list|security.force_subscribe_channels" for d in datas)
    assert not any("set|edit|security.force_subscribe_channels" in d for d in datas)


# ── list manager screen (add/remove) ─────────────────────────────────────────

def test_list_screen_has_add_and_per_entry_delete():
    screen = list_screen("lelouch", "security", "force_subscribe_channels",
                         [-1001111111111, -1002222222222])
    flat = [b for row in screen.keyboard.inline_keyboard for b in row]
    datas = [b.callback_data for b in flat]
    # One delete per entry, indexed 0..n-1, plus an Add button.
    assert "lelouch|set|ldel|security.force_subscribe_channels|0" in datas
    assert "lelouch|set|ldel|security.force_subscribe_channels|1" in datas
    assert "lelouch|set|ladd|security.force_subscribe_channels" in datas


def test_list_screen_empty_shows_hint_and_add():
    screen = list_screen("lelouch", "security", "force_subscribe_channels", [])
    datas = [b.callback_data for row in screen.keyboard.inline_keyboard for b in row]
    assert "lelouch|set|ladd|security.force_subscribe_channels" in datas
    # No delete rows when the list is empty.
    assert not any("ldel" in d for d in datas)


def test_field_screen_append_mode_asks_for_single_value():
    screen = field_screen("lelouch", "security", "force_subscribe_channels",
                          [], "list", widget="channel", mode="append")
    # Append mode must NOT invite a comma-separated list (that was the old
    # replace-everything behaviour); Cancel returns to the list manager.
    datas = [b.callback_data for row in screen.keyboard.inline_keyboard for b in row]
    assert any("set|list|security.force_subscribe_channels" in d for d in datas)
