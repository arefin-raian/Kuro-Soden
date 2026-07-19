"""Human-friendly settings engine shared by all four Kuro Sōden bots.

The old panels leaked developer vocabulary at the user: raw field slugs
(``concurrent_downloads``), bare template tokens (``{title}``), literal ``\\n``,
and dead ``/dlset key=value`` command hints. A person who doesn't write code
could not tell what any of it meant. Worse, only Levi and the admin bot actually
*wrote* values — Senku and Gojo just told the user to "open the NekoFetch admin
bot", which is not a setting, it's a scavenger hunt.

This module is the single home for the settings experience, so all four bots
behave identically and there is no 4× drift:

* :func:`parse_user_markup` — accept whatever styling a normal person sends.
  Telegram-native bold/italic (selected in the app), raw HTML tags, or Markdown
  (``*bold*``, ``_italic_``, `` `code` ``) — all auto-detected and normalised to
  the Telegram HTML the renderers expect. Real line breaks are kept; a typed
  literal ``\\n`` is turned into a real newline (people type that expecting a
  break).
* :func:`render_sample` — fill a template with realistic sample data so the user
  SEES how the card/post will look before saving, instead of decoding tokens.
* :func:`register_settings` — wire a bot's whole settings surface (hub → section
  → field card → live edit) onto the real :class:`SettingsService`, so every
  change persists and applies live. Owner-only sections stay gated.

Nothing here talks to Telegram directly except inside ``register_settings``; the
builders and parsers are pure and unit-tested in ``tests/test_settings_ui.py``.
"""

from __future__ import annotations

import html as _html
import re
from typing import Iterable, Sequence

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.settings_schema import (
    doc_for,
    is_owner_only,
    label_for,
    widget_for,
)
from nekofetch.domain.enums import Permission
from nekofetch.services.auth_service import AuthService
from nekofetch.services.settings_service import SettingsService
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.components import cb, edit_markup, keyboard
from nekofetch.ui.screens import Screen, send_screen


# ─────────────────────────────────────────────────────────────────────────────
# Input parsing — accept Telegram-native styling, HTML, or Markdown
# ─────────────────────────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def _looks_like_html(text: str) -> bool:
    """True if the raw text already carries HTML tags the user typed by hand."""
    return bool(_HTML_TAG_RE.search(text))


def _markdown_to_html(text: str) -> str:
    """Convert the common Markdown a person is likely to type into Telegram HTML.

    Handles (in a safe order so markers don't cross-eat each other): inline code,
    links, bold, italic, underline, strike, spoiler. Anything that isn't a marker
    is left exactly as typed, so plain prose passes through untouched.
    """
    # 1) Inline code first — its contents must NOT be re-parsed for other markers.
    #    Stash each span, drop in a placeholder, restore at the very end.
    stash: list[str] = []

    def _stash_code(m: "re.Match[str]") -> str:
        stash.append(m.group(1))
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash_code, text)

    # 2) Links [label](url) → <a href="url">label</a>
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )

    # 3) Bold: **x** or __x__  (double markers before single so they win)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    # 4) Strike ~~x~~ and spoiler ||x|| (double markers)
    text = re.sub(r"~~([^~]+)~~", r"<s>\1</s>", text)
    text = re.sub(r"\|\|([^|]+)\|\|", r'<span class="tg-spoiler">\1</span>', text)
    # 5) Italic single *x* or _x_ (after bold/underline doubles are gone)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!_)_(?!_)([^_\n]+)_(?!_)", r"<i>\1</i>", text)

    # Restore stashed code spans as <code>…</code> (escaped — code is literal).
    def _restore(m: "re.Match[str]") -> str:
        return f"<code>{_html.escape(stash[int(m.group(1))])}</code>"

    text = re.sub(r"\x00(\d+)\x00", _restore, text)
    return text


def _normalise_newlines(text: str) -> str:
    r"""Turn a typed literal ``\n`` (backslash-n) into a real newline.

    People who don't code type ``\n`` expecting a line break, or just press
    Enter. Real newlines are already preserved by Telegram; here we only rescue
    the literal escape so both habits produce the same visible break. Windows
    ``\r\n`` is normalised to ``\n`` too.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Literal backslash-n / backslash-t that a user typed as text.
    text = text.replace("\\n", "\n").replace("\\t", "    ")
    return text


def parse_user_markup(message: Message) -> str:
    """Return the value to store from a settings-edit message, styling preserved.

    Auto-detects, in priority order:
      1. Raw HTML the user typed by hand (``<b>…</b>``) → kept as-is.
      2. Telegram-native styling (bold/italic chosen in the app) → the message's
         HTML rendering, which encodes those entities as tags.
      3. Markdown (``*bold*``, ``_i_``, `` `code` ``) → converted to HTML.
      4. Plain text → passed through.

    In every case, real newlines are kept and a literal ``\\n`` becomes a break.
    """
    raw = message.text if message.text is not None else (message.caption or "")
    raw = str(raw)

    # 1) Hand-typed HTML wins — respect exactly what they wrote.
    if _looks_like_html(raw):
        return _normalise_newlines(raw)

    # 2) Native Telegram styling → entities. Pyrogram exposes an HTML rendering
    #    on the Str subclass; use it only when entities are actually present, so
    #    plain text isn't needlessly HTML-escaped.
    entities = message.entities or message.caption_entities
    if entities:
        source = message.text or message.caption
        html_version = getattr(source, "html", None)
        if html_version:
            return _normalise_newlines(str(html_version))

    # 3) Markdown markers → HTML. 4) otherwise plain prose falls through cleanly.
    return _normalise_newlines(_markdown_to_html(raw))


# ─────────────────────────────────────────────────────────────────────────────
# Live sample rendering — show, don't tell
# ─────────────────────────────────────────────────────────────────────────────

# Realistic sample values for every template token the schema advertises. The
# preview fills any token present in a template, so an operator sees a real card
# instead of decoding ``{synopsis}``. Unknown tokens are left intact so a typo is
# visible rather than silently blanked.
_SAMPLE: dict[str, str] = {
    "{title}": "Attack on Titan",
    "{romaji}": "Shingeki no Kyojin",
    "{short_title}": "AoT",
    "{genres}": "Action, Drama, Fantasy",
    "{format}": "TV",
    "{type}": "TV",
    "{content_type}": "Season",
    "{rating}": "8.5",
    "{status}": "Finished",
    "{first_aired}": "Apr 7, 2013",
    "{last_aired}": "Nov 4, 2023",
    "{runtime}": "24 min",
    "{episodes}": "25",
    "{synopsis}": "Humanity lives behind towering walls, hunted by man-eating Titans.",
    "{overview}": "Humanity lives behind towering walls, hunted by man-eating Titans.",
    "{season}": "1",
    "{season_part}": "",
    "{season_label}": "Season 1",
    "{S}": "S",
    "{language}": "Dual",
    "{languages}": "Sub, Dual",
    "{duration}": "1h 35m",
    "{qualities}": "480p, 720p, 1080p",
    "{quality}": "1080p",
    "{resolution}": "1080p",
    "{res}": "1080p",
    "{audio}": "Dual",
    "{label}": "Movie",
    "{tag}": "AttackOnTitan",
    "{group}": "AniXWeebs",
    "{source}": "miruro",
    "{episode}": "07",
    "{episode_from}": "01",
    "{episode_to}": "25",
    "{letter}": "A",
    "{lang}": "Japanese",
    "{h}": "1",
    "{m}": "35",
}

# {seasons} is a composed block (the watch-guide wrapper injects assembled lines);
# give it a believable two-line sample so the wrapper preview reads naturally.
_SAMPLE_SEASONS = (
    "<b>➥ Season 1 [ 25 Episodes ]</b>\n      480p, 720p, 1080p\n"
    "<b>➥ Movie [ 1 Episode ]</b>\n      720p, 1080p"
)
_SAMPLE_ENTRIES = "⦿ Attack on Titan\n⦿ Akame ga Kill"


def render_sample(template: str) -> str:
    """Fill ``template`` with sample data and normalise newlines for preview.

    Pure and side-effect free: used both by the live panel and the tests. Tokens
    the sample set doesn't know are left as-is so mistakes stay visible.
    """
    out = _normalise_newlines(template or "")
    out = out.replace("{seasons}", _SAMPLE_SEASONS).replace("{entries}", _SAMPLE_ENTRIES)
    for token, value in _SAMPLE.items():
        if token in out:
            out = out.replace(token, value)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Human labels — never show a raw field slug
# ─────────────────────────────────────────────────────────────────────────────

# Section slug → friendly (emoji + words) label. Any section not listed falls
# back to a title-cased slug, so adding a section never crashes the panel.
SECTION_LABELS: dict[str, str] = {
    "features": "✨ Features",
    "downloads": "⬇️ Downloads",
    "acquisition": "🎯 What to Fetch",
    "processing": "⚙️ Processing",
    "rename": "✎ File Names",
    "metadata": "🏷 File Info",
    "thumbnail": "🖼 Thumbnails",
    "watermark": "💧 Watermark",
    "branding": "✦ Branding",
    "distribution": "📤 Delivery",
    "queue": "📊 Queue",
    "security": "🔒 Access",
    "post_format": "🎨 How Posts Look",
    "bot": "🤖 Bot & Footer",
    "main_channel": "📢 Main Channel",
    "index_channel": "🔤 Index Channel",
    "thumbnail_channel": "🎬 Thumbnail Channel",
    # Owner-only / infrastructure sections (admin bot surfaces these too).
    "sources": "🌐 Sources",
    "access": "👥 Access & Roles",
    "shortlink": "🔗 Shortlinks",
    "storage_channel": "🗄 Storage Channel",
    "log_channel": "📋 Control Center",
    "ui": "🎛 Interface",
    "localization": "🌍 Language",
}

# A handful of field slugs whose auto-humanised name would still read oddly.
_FIELD_LABELS: dict[str, str] = {
    "concurrent_downloads": "Downloads at Once",
    "retry_attempts": "Retry Attempts",
    "retry_backoff_seconds": "Wait Between Retries",
    "resume_interrupted": "Resume Interrupted Files",
    "progress_update_interval_seconds": "Progress Refresh (seconds)",
    "target_resolutions": "Qualities to Grab",
    "resolution_fallbacks": "Quality Fallbacks",
    "require_english_subs": "Require English Subs",
    "verify_files": "Verify Files",
    "require_approval_before_publish": "Approve Before Publish",
    "info_card_template": "Info Card Look",
    "season_card_template": "Season Card Look",
    "movie_card_template": "Movie Card Look",
    "extras_card_template": "Extras Card Look",
    "watch_guide_template": "Watch Guide Look",
    "watch_guide_season_line": "Watch Guide — Season Line",
    "watch_guide_extra_line": "Watch Guide — Extra Line",
    "footer_template": "Footer Text",
    "footer_image_url": "Footer Image",
    "resolution_label": "Quality Button Label",
    "buttons_per_row": "Buttons per Row",
    "max_quality_buttons": "Max Quality Buttons",
    "language_label_japanese": "Japanese Section Label",
    "language_label_english": "English Section Label",
    "japanese_first": "Show Japanese First",
    "pin_info_card": "Pin the Info Card",
    "pin_watch_guide": "Pin the Watch Guide",
    "divider_sticker_id": "Divider Sticker",
    "caption_template": "Post Caption Look",
    "index_button_text": "Index Button Text",
    "download_button_text": "Download Button Text",
    "letter_header_template": "Letter Header Look",
    "entry_template": "Catalog Line Look",
    "force_subscribe": "Require Channel Join",
    "dist_force_subscribe": "Require Join (Delivery Bots)",
    "request_system": "Accept Requests",
}


def field_label(field: str, section: str | None = None) -> str:
    """Friendly, human label for a config field (never the raw slug).

    Priority: schema-authored ``label`` (needs the section) → the local
    ``_FIELD_LABELS`` map → a title-cased slug. The section is optional so old
    call sites that only have the field still work.
    """
    if section is not None:
        schema_label = label_for(section, field)
        if schema_label:
            return schema_label
    return _FIELD_LABELS.get(field, field.replace("_", " ").title())


def section_label(section: str) -> str:
    return SECTION_LABELS.get(section, section.replace("_", " ").title())


def _forwarded_chat_id(message: Message) -> int | None:
    """Extract the origin chat id from a forwarded message, if present.

    Pyrogram exposes the origin as ``forward_from_chat`` (older) — we read the id
    off it defensively so a forwarded post from a channel yields ``-100…`` without
    the operator having to know the id. Returns ``None`` when there's no channel
    origin to read.
    """
    chat = getattr(message, "forward_from_chat", None)
    cid = getattr(chat, "id", None)
    return int(cid) if cid is not None else None


def _shorten(value: object, limit: int = 22) -> str:
    if isinstance(value, list):
        s = ", ".join(map(str, value)) or "—"
    elif isinstance(value, bool):
        s = "on" if value else "off"
    else:
        s = str(value) if value not in (None, "") else "—"
    s = s.replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ─────────────────────────────────────────────────────────────────────────────
# Screen builders (pure) — hub, section, field card
# ─────────────────────────────────────────────────────────────────────────────

_ICON = {"lelouch": "🎭", "levi": "⚔️", "senku": "🧪", "gojo": "🔮"}


def _bot_icon(bot: str) -> str:
    return _ICON.get(bot, "🤖")


def hub_screen(
    bot: str, title: str, blurb: str, sections: Sequence[str],
    *, extra_buttons: Sequence[tuple[str, str]] = (),
) -> Screen:
    """The settings root: a friendly section list, two buttons per row.

    ``extra_buttons`` (``[(label, callback_data), …]``) are appended above Back —
    used for per-admin surfaces (e.g. "My Timezone") that live outside the
    config-backed sections.
    """
    rows: list[list[tuple[str, str]]] = []
    labelled = [(section_label(s), s) for s in sections]
    for i in range(0, len(labelled), 2):
        rows.append([(lbl, cb(bot, "set", "sec", s)) for lbl, s in labelled[i : i + 2]])
    for lbl, data in extra_buttons:
        rows.append([(lbl, data)])
    rows.append([("⇐ Back", cb(bot, "home"))])
    caption = (
        f"{_bot_icon(bot)}  <b>{title}</b>\n\n"
        f"{blurb}\n\n"
        "<i>Tap a section. On/off switches flip right here; anything with text "
        "opens a simple editor that shows you an example first.</i>"
    )
    return Screen(caption=caption, image=pick_artwork(bot), keyboard=keyboard(*rows))


def _section_rows(svc: SettingsService, bot: str, section: str) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    for field, value, kind in svc.section_fields(section):
        label = field_label(field, section)
        widget = widget_for(section, field, value)
        if widget == "toggle":
            mark = "🟢" if value else "⚪️"
            rows.append([(f"{mark}  {label}", cb(bot, "set", "tog", f"{section}.{field}"))])
        elif widget == "choice":
            # Fixed value set → open the tap-to-pick screen (no free-text typos).
            rows.append([(f"{label}  ·  {_shorten(value)}",
                          cb(bot, "set", "pick", f"{section}.{field}"))])
        else:
            # text / number / list / template / channel / sticker / timezone all
            # open the edit card, which adapts its capture to the widget.
            rows.append([(f"{label}  ·  {_shorten(value)}",
                          cb(bot, "set", "edit", f"{section}.{field}"))])
    rows.append([("⇐ Back", cb(bot, "set", "home"))])
    return rows


def section_screen(svc: SettingsService, bot: str, section: str) -> Screen:
    caption = (
        f"{_bot_icon(bot)}  <b>{section_label(section)}</b>\n\n"
        "🟢 = on · ⚪️ = off — tap to flip.\n"
        "Rows with text open an editor that shows an example before you type."
    )
    return Screen(caption=caption, image=pick_artwork(bot),
                  keyboard=keyboard(*_section_rows(svc, bot, section)))


def field_screen(
    bot: str, section: str, field: str, current: object, kind: str,
    *, widget: str | None = None,
) -> Screen:
    """The human-friendly editor card for one setting.

    Shows, in plain language: what it does, (for templates) a LIVE preview of how
    the post will look filled with real sample data, the variables you can drop in
    with plain descriptions, what it's set to now, and how to change it. No raw
    field slugs, no bare tokens, no ``/command`` syntax.

    ``widget`` tailors the closing instruction: ``channel`` invites forwarding a
    message or pasting an id, ``sticker`` invites sending the sticker itself, and
    everything else keeps the "send your new value" prompt.
    """
    doc = doc_for(section, field)
    label = field_label(field, section)
    parts: list[str] = [f"{_bot_icon(bot)}  <b>{label}</b>", ""]

    desc = doc.desc if doc else f"Sets “{label}”."
    parts.append(f"<blockquote>{desc}</blockquote>")

    is_template = bool(doc and doc.placeholders)
    # Live preview: for templates, render the CURRENT value (or the schema
    # example if the current is empty) with real sample data.
    if is_template:
        sample_src = ""
        if isinstance(current, str) and current.strip():
            sample_src = current
        elif doc and doc.example:
            sample_src = doc.example
        if sample_src:
            parts += ["", "<b>Preview — how it will look:</b>",
                      f"<blockquote>{render_sample(sample_src)}</blockquote>"]

    # Choices (enum-like fields) with plain-language meaning.
    if doc and doc.option_notes:
        parts += ["", "<b>Choices:</b>"]
        parts += [f"  • <code>{_html.escape(val)}</code> — {note}"
                  for val, note in doc.option_notes.items()]
    elif doc and doc.options:
        parts += ["", "<b>Allowed:</b> " + " · ".join(f"<code>{_html.escape(o)}</code>"
                                                       for o in doc.options)]

    # Variables you can use, in plain words.
    if doc and doc.placeholders:
        parts += ["", "<b>You can drop in:</b>"]
        parts += [f"  • <code>{_html.escape(var)}</code> — {expl}"
                  for var, expl in doc.placeholders.items()]

    if is_template:
        parts += ["", "<i>Style it any way you like — pick text and use Telegram's "
                  "bold/italic, or type it plain. Press Enter for line breaks.</i>"]

    shown = ", ".join(map(str, current)) if isinstance(current, list) else str(current or "—")
    parts += ["", f"<b>Right now:</b> <code>{_html.escape(shown)}</code>"]

    if widget == "channel":
        parts += ["", "<i>Forward any message from the channel, or paste its id "
                  "(the long -100… number). Send /cancel to keep it.</i>"]
    elif widget == "sticker":
        parts += ["", "<i>Send the sticker itself and I'll grab its id, or paste "
                  "a file_id. Send /cancel to keep it, or “none” to clear it.</i>"]
    else:
        tail = " (separate several with commas)" if kind == "list" else ""
        parts += ["", f"<i>Send your new value as a message{tail}. Send /cancel to keep it.</i>"]

    kb = keyboard([("✗ Cancel", cb(bot, "set", "sec", section))])
    return Screen(caption="\n".join(parts), image=pick_artwork(bot), keyboard=kb)


def choice_screen(bot: str, section: str, field: str, current: object) -> Screen:
    """A tap-to-pick card for an enum-like field. One button per allowed value,
    the current pick marked, so a typo can never store garbage into the field.

    The schema's ``option_notes`` (value → meaning) are listed in the caption so
    the operator knows what each choice does before tapping.
    """
    doc = doc_for(section, field)
    label = field_label(field, section)
    parts: list[str] = [f"{_bot_icon(bot)}  <b>{label}</b>", ""]
    desc = doc.desc if doc else f"Sets “{label}”."
    parts.append(f"<blockquote>{desc}</blockquote>")

    options = list(doc.options) if doc else []
    if doc and doc.option_notes:
        parts += ["", "<b>Choices:</b>"]
        parts += [f"  • <code>{_html.escape(val)}</code> — {note}"
                  for val, note in doc.option_notes.items()]

    cur = str(current) if current not in (None, "") else ""
    parts += ["", f"<b>Right now:</b> <code>{_html.escape(cur or '—')}</code>",
              "", "<i>Tap a choice to set it.</i>"]

    rows: list[list[tuple[str, str]]] = []
    for opt in options:
        mark = "🔘 " if opt == cur else "▫️ "
        rows.append([(f"{mark}{opt}", cb(bot, "set", "opt", f"{section}.{field}", opt))])
    rows.append([("✗ Cancel", cb(bot, "set", "sec", section))])
    return Screen(caption="\n".join(parts), image=pick_artwork(bot), keyboard=keyboard(*rows))


# ─────────────────────────────────────────────────────────────────────────────
# Registration — wire the whole surface onto SettingsService
# ─────────────────────────────────────────────────────────────────────────────

def register_settings(
    client: Client,
    container: Container,
    bot: str,
    sections: Iterable[str],
    *,
    title: str,
    blurb: str,
    group: int = 0,
    input_group: int = 5,
    extra_buttons: Sequence[tuple[str, str]] = (),
) -> None:
    """Wire ``bot``'s settings hub/section/field/edit flow onto real config.

    ``sections`` are the config sections this bot owns (each must exist on
    ``AppConfig``; missing ones are dropped). Callback namespace is ``{bot}|set|``
    and the free-text edit capture runs in ``input_group`` so it doesn't fight
    the bot's other message handlers. Permissions and owner-only gating mirror
    the admin/Levi panels. ``extra_buttons`` are appended to the hub for per-admin
    surfaces that live outside config (e.g. the timezone picker).
    """
    sections = list(sections)
    extra_buttons = list(extra_buttons)
    auth = AuthService(container)
    svc = SettingsService(container)
    fsm = FSM(container.redis, bot=bot)
    state_edit = f"{bot}_settings:edit"

    def _live_sections() -> list[str]:
        return [s for s in sections if svc.section(s) is not None]

    def _allowed(user) -> bool:
        return bool(user and auth.has_permission(user, Permission.CONFIGURE))

    async def _deny(q: CallbackQuery, section: str | None = None) -> bool:
        user = getattr(q, "nf_user", None)
        if not _allowed(user):
            await q.answer(f"You don't have permission to configure {bot.title()}.",
                           show_alert=True)
            return True
        if section and is_owner_only(section) and not auth.is_owner(user):
            await q.answer("That section is owner-only.", show_alert=True)
            return True
        return False

    def _hub(user=None) -> Screen:
        # Owner-only sections are hidden outright from non-owners (not just gated
        # on tap), so the hub reads the same as the old admin panel did.
        is_owner = auth.is_owner(user) if user is not None else True
        sections = [s for s in _live_sections()
                    if is_owner or not is_owner_only(s)]
        return hub_screen(bot, title, blurb, sections, extra_buttons=extra_buttons)

    # ── hub ──────────────────────────────────────────────────────────────────
    # Both ``{bot}|set|home`` (Back-from-section) and the bare ``{bot}|settings``
    # a start-menu button emits land on the same friendly hub, so no settings tap
    # can dead-end.
    @client.on_callback_query(
        filters.regex(rf"^{bot}\|(set\|home|settings)$"), group=group
    )
    async def _on_home(_: Client, q: CallbackQuery) -> None:
        if await _deny(q):
            return
        await q.answer()
        await send_screen(client, q.message.chat.id,
                          _hub(getattr(q, "nf_user", None)), old_msg=q.message)

    # ── one section ────────────────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(rf"^{bot}\|set\|sec\|"), group=group)
    async def _on_section(_: Client, q: CallbackQuery) -> None:
        section = q.data.split("|", 3)[3]
        if await _deny(q, section):
            return
        await q.answer()
        await send_screen(client, q.message.chat.id,
                          section_screen(svc, bot, section), old_msg=q.message)

    # ── toggle a boolean in place ────────────────────────────────────────────
    @client.on_callback_query(filters.regex(rf"^{bot}\|set\|tog\|"), group=group)
    async def _on_toggle(_: Client, q: CallbackQuery) -> None:
        key = q.data.split("|", 3)[3]
        section, field = key.split(".", 1)
        if await _deny(q, section):
            return
        new_val = await svc.toggle(section, field)
        await q.answer(f"{field_label(field, section)} → {'on' if new_val else 'off'}")
        await edit_markup(q, _section_rows(svc, bot, section))

    # ── open a field editor ──────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(rf"^{bot}\|set\|edit\|"), group=group)
    async def _on_edit(_: Client, q: CallbackQuery) -> None:
        key = q.data.split("|", 3)[3]
        section, field = key.split(".", 1)
        if await _deny(q, section):
            return
        current = getattr(svc.section(section), field, "")
        kind = "list" if isinstance(current, list) else "value"
        widget = widget_for(section, field, current)
        # Remember the widget so the message capture knows to read a sticker id or
        # a forwarded channel id rather than the raw text.
        await fsm.set(q.from_user.id, state_edit, section=section, field=field,
                      widget=widget)
        await q.answer()
        await send_screen(client, q.message.chat.id,
                          field_screen(bot, section, field, current, kind, widget=widget),
                          old_msg=q.message)

    # ── open a choice picker (enum-like field) ────────────────────────────────
    @client.on_callback_query(filters.regex(rf"^{bot}\|set\|pick\|"), group=group)
    async def _on_pick(_: Client, q: CallbackQuery) -> None:
        key = q.data.split("|", 3)[3]
        section, field = key.split(".", 1)
        if await _deny(q, section):
            return
        current = getattr(svc.section(section), field, "")
        await q.answer()
        await send_screen(client, q.message.chat.id,
                          choice_screen(bot, section, field, current), old_msg=q.message)

    # ── apply a chosen option ─────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(rf"^{bot}\|set\|opt\|"), group=group)
    async def _on_opt(_: Client, q: CallbackQuery) -> None:
        # data: {bot}|set|opt|{section}.{field}|{value}
        _, _, _, key, value = q.data.split("|", 4)
        section, field = key.split(".", 1)
        if await _deny(q, section):
            return
        try:
            await svc.set_value(section, field, value)
        except (ValueError, KeyError, TypeError):
            await q.answer("Couldn't set that choice.", show_alert=True)
            return
        await q.answer(f"{field_label(field, section)} → {value}")
        await send_screen(client, q.message.chat.id,
                          choice_screen(bot, section, field, value), old_msg=q.message)

    # ── capture the typed / sent value ────────────────────────────────────────
    # Text covers every widget; stickers and forwarded messages let the guided
    # ``sticker``/``channel`` widgets capture an id without the user copy-pasting.
    @client.on_message(
        (filters.text | filters.sticker | filters.forwarded)
        & filters.private & ~filters.command(["start", "cancel"]),
        group=input_group,
    )
    async def _on_input(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, data = await fsm.get(message.from_user.id)
        if state != state_edit:
            return
        user = getattr(message, "nf_user", None)
        if not _allowed(user):
            return
        section, field = data.get("section"), data.get("field")
        widget = data.get("widget")
        if is_owner_only(section) and not auth.is_owner(user):
            await fsm.clear(message.from_user.id)
            await message.reply("That section is owner-only.", parse_mode=ParseMode.HTML)
            return

        # Guided widgets: pull the id out of the sticker / forwarded message before
        # falling back to typed text. A wrong message type just re-prompts and
        # keeps the edit state alive so the next send still lands.
        raw: str | None = None
        if widget == "sticker":
            if message.sticker:
                raw = message.sticker.file_id
            elif message.text:
                t = message.text.strip()
                raw = "" if t.lower() in ("none", "clear", "-") else t
        elif widget == "channel":
            fwd = _forwarded_chat_id(message)
            if fwd is not None:
                raw = str(fwd)
            elif message.text:
                raw = message.text.strip()
        if raw is None and message.text is None:
            # e.g. a sticker sent to a text field — guide, don't crash.
            await message.reply(
                "That doesn't fit this setting. Send it as text, or /cancel.",
                parse_mode=ParseMode.HTML,
            )
            return

        await fsm.clear(message.from_user.id)

        current = getattr(svc.section(section), field, None)
        if raw is None:
            # Templates/text keep their styling; scalars and lists take the plain
            # text so number/bool/list coercion in set_typed sees clean input.
            if isinstance(current, (bool, int, float, list)):
                raw = str(message.text or "").strip()
            else:
                raw = parse_user_markup(message)
        try:
            value = await svc.set_typed(section, field, raw)
        except (ValueError, KeyError, TypeError):
            await message.reply(
                "Hmm, that didn't look right for this setting. "
                "Check the example on the card and try again.",
                parse_mode=ParseMode.HTML,
            )
            return

        shown = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        confirm = [f"✅ <b>{field_label(field, section)}</b> saved."]
        doc = doc_for(section, field)
        if isinstance(value, str) and doc and doc.placeholders and value.strip():
            confirm += ["", "<b>Preview:</b>", f"<blockquote>{render_sample(value)}</blockquote>"]
        else:
            confirm += ["", f"Now set to: <code>{_html.escape(shown)}</code>"]
        await message.reply(
            "\n".join(confirm),
            reply_markup=keyboard([("⇐ Back", cb(bot, "set", "sec", section))]),
            parse_mode=ParseMode.HTML,
        )

    # ── /settings opens the hub ───────────────────────────────────────────────
    @client.on_message(filters.command("settings") & filters.private, group=group)
    async def _on_settings_cmd(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        user = getattr(message, "nf_user", None)
        if not _allowed(user):
            await message.reply(
                f"You don't have permission to configure {bot.title()}.",
                parse_mode=ParseMode.HTML,
            )
            return
        await send_screen(client, message.chat.id, _hub(user))

    # ── /cancel bails out of an in-progress edit ─────────────────────────────
    @client.on_message(filters.command("cancel") & filters.private, group=input_group)
    async def _on_cancel(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, _data = await fsm.get(message.from_user.id)
        if state == state_edit:
            await fsm.clear(message.from_user.id)
            await message.reply("Okay, left it unchanged.", parse_mode=ParseMode.HTML)
