"""Per-bot settings content for the four Kuro Soden pipeline bots.

Each entry is the data the menu dispatcher feeds into
:func:`kurosoden.shared.menu_router.settings_onboarding` once the user taps a
key on the bot's settings hub. Modeled after NekoFetch's own settings
edit-prompt UX (see ``nekofetch.bots.admin.handlers.settings._edit_prompt``)
so admins coming from either bot feel at home.

Keys:
    title            — Section title shown bold at the top of the panel.
    about            — One-paragraph description (rendered in a blockquote).
    when_to_use      — Optional hint about WHEN this setting matters.
    options          — Optional list of (value, description) when the field
                       is closed-set (e.g. dual-audio strategy).
    placeholders     — Optional list of (var, description) for templates
                       (e.g. caption template {title}/{code}/{score}).
    supports_html    — If True, marks the field as accepting HTML markup.
    example          — A literal example string shown in a blockquote.
    danger           — Optional warning text shown in italics.
    hint             — How to apply the new value (chat message).
    current          — Optional, current value hint.
"""

from __future__ import annotations


# ── lelouch ───────────────────────────────────────────────────────────────────

LELOUCH = {
    "limits": {
        "title": "Request Limits",
        "about": (
            "Maximum number of active pipeline requests a regular user can hold "
            "at once. Staff bypass this limit so they can batch."
        ),
        "when_to_use": (
            "When downloads slow down because one user hogged the pipeline, or "
            "when you want to invite more users but keep queue fairness."
        ),
        "options": [
            ("0", "Pause all incoming requests (use only during maintenance)."),
            ("1", "Strict — the safest fairness setting."),
            ("2", "Comfortable default; one user can't dominate."),
            ("3+", "Loose — favoured whales, but queue pressure rises."),
        ],
        "example": "/limit max_requests=2",
        "hint": (
            "Send the new value as a chat message — "
            "<code>/limit max_requests=&lt;N&gt;</code> is the canonical form, "
            "or just send a number and I'll pick it up."
        ),
        "danger": (
            "Setting this to 0 will pause incoming requests from regular users."
        ),
    },

    "admins": {
        "title": "Admin Pool",
        "about": (
            "How many downloader admins are in the rotation and how their "
            "weights bias assignment. New admins join with weight 1.0; bump "
            "trusted ones higher so they get more tasks."
        ),
        "when_to_use": (
            "Whenever an admin joins/leaves, or when one admin keeps "
            "falling behind while another is light."
        ),
        "example": "/admin set_weight @hanzo 1.5",
        "hint": (
            "Send <code>/admin set_weight @username &lt;weight&gt;</code> "
            "where weight is a decimal (0.5–2.0)."
        ),
    },
}


# ── levi ──────────────────────────────────────────────────────────────────────

LEVI = {
    "downloads": {
        "title": "Download Settings",
        "about": (
            "How many parallel downloads run at once, how aggressively we "
            "retry transient host failures, and which quality we prefer when "
            "multiple resolutions are available."
        ),
        "when_to_use": (
            "If downloads stall (lower concurrency) or if a provider keeps "
            "rate-limiting (boost retries)."
        ),
        "options": [
            ("concurrentDownloads=1", "Safest — one file at a time."),
            ("concurrentDownloads=3", "Default — sweet spot for most hosts."),
            ("concurrentDownloads=5", "Aggressive — only on whitelisted hosts."),
            ("preferredQuality=720p", "Lower bandwidth; smaller files."),
            ("preferredQuality=1080p", "Default — best balance."),
            ("preferredQuality=2160p", "4K, only when explicitly requested."),
            ("retryCount=3", "Conservative — fail fast on bad hosts."),
            ("retryCount=6", "Default — recovers from common flaps."),
            ("retryCount=10", "Paranoid — burns time but rarely loses jobs."),
        ],
        "example": "/dlset concurrentDownloads=3 preferredQuality=1080p",
        "hint": (
            "Send one or more key=value pairs as a single message; "
            "the worker reloads on the next job pickup."
        ),
    },

    "processing": {
        "title": "Processing Options",
        "about": (
            "Which container we output, how we brand the watermark stamp, "
            "and which dual-audio strategy we apply when both English dub "
            "and Japanese audio are present."
        ),
        "when_to_use": (
            "Whenever a server-side ffmpeg complaint lands in the log channel, "
            "or when staff requests a different branding style per franchise."
        ),
        "options": [
            ("outputContainer=mp4", "Default — fast streaming, broad device support."),
            ("outputContainer=mkv", "Lossless archival — for niche collectors."),
            ("dualAudioStrategy=keep_eng_jp", "Default — keeps both tracks."),
            ("dualAudioStrategy=keep_jp_only", "Original-audio purist."),
            ("dualAudioStrategy=keep_eng_only", "Dub-only release."),
            (
                "brandingTemplate=kuro_soden_v2",
                "Default — top-right 8% watermark.",
            ),
        ],
        "example": "/procset dualAudioStrategy=keep_eng_jp",
        "hint": (
            "Send the setting name(s) as one message — "
            "<code>/procset key=value key=value ...</code>."
        ),
        "danger": (
            "Changing the container mid-run will reject in-flight jobs (they "
            "restart next pickup)."
        ),
    },
}


# ── senku ─────────────────────────────────────────────────────────────────────

SENKU = {
    "branding": {
        "title": "Channel Branding",
        "about": (
            "The footer post appended to every distribution channel, the "
            "divider sticker between sections, and the suffix used when new "
            "bot usernames are minted. These live in the NekoFetch admin "
            "Settings panel under <b>post_format</b> and <b>bot</b>; leaving "
            "a footer field empty falls back to the built-in default."
        ),
        "when_to_use": (
            "When a new visual identity drops, or when you want the footer to "
            "link the brand account."
        ),
        "options": [
            ("post_format.footer_template", "Footer card text (empty = default)."),
            ("post_format.footer_image_url", "Footer image — URL or file_id."),
            ("post_format.divider_sticker_id",
             "Sticker between sections (empty = bot.divider_sticker_id)."),
            ("bot.bot_username_suffix", "Suffix for generated bot usernames."),
        ],
        "supports_html": True,
        "example": "post_format.footer_template = Join @KuroSoden for more ✦",
        "hint": (
            "Open the <b>NekoFetch admin bot → Settings → post_format</b> to "
            "change these; every field there carries its own help panel."
        ),
    },

    "layout": {
        "title": "Content Layout",
        "about": (
            "Templates and layout for every auto-generated card — info, "
            "season, movie, watch guide — plus the quality-button rows, the "
            "resolution label, the language-section order, and which cards "
            "are pinned. All configured under <b>post_format</b> in the "
            "NekoFetch admin Settings panel; empty template = built-in look."
        ),
        "when_to_use": (
            "Before launching a new show, or after feedback that the channel "
            "feels too dense / too sparse."
        ),
        "options": [
            ("post_format.info_card_template", "Franchise info/overview card."),
            ("post_format.season_card_template", "Per-season (multi-episode) card."),
            ("post_format.movie_card_template",
             "Movie/single-episode card — shows runtime, not episode count."),
            ("post_format.watch_guide_template", "Watch-guide wrapper + lines."),
            ("post_format.buttons_per_row",
             "Quality buttons per row (2 = reference: 3→[2,1])."),
            ("post_format.resolution_label", "Button label wrapper, e.g. 「 {res} 」."),
            ("post_format.japanese_first",
             "Show the original-audio section first (sub-only titles)."),
            ("post_format.pin_info_card / pin_watch_guide", "Which cards pin."),
        ],
        "placeholders": [
            ("{title}", "Anime / entry title."),
            ("{episodes}", "Episode count."),
            ("{duration}", "Runtime from AniList minutes (movie card only)."),
            ("{rating}", "AniList score."),
            ("{genres}", "Genre list."),
            ("{synopsis}", "Trimmed synopsis."),
            ("{seasons}", "Assembled watch-guide lines (guide wrapper only)."),
        ],
        "supports_html": True,
        "example": "post_format.movie_card_template = <b>{title}</b>\\n⏱ {duration}",
        "hint": (
            "Open the <b>NekoFetch admin bot → Settings → post_format</b>. Each "
            "template lists the exact variables it supports in its help panel."
        ),
    },
}


# ── gojo ──────────────────────────────────────────────────────────────────────

GOJO = {
    "caption": {
        "title": "Caption Template",
        "about": (
            "The HTML template that wraps every public main-channel post. "
            "Configured under <b>main_channel.caption_template</b> in the "
            "NekoFetch admin Settings panel. Use the <code>{placeholder}</code> "
            "tokens below — they expand at publish time."
        ),
        "when_to_use": (
            "Whenever you want a consistent voice across all posts, or "
            "before a special event (e.g. anniversary caption)."
        ),
        "placeholders": [
            ("{title}", "Anime title (English when available, else original)."),
            ("{tag}", "Hashtag-safe title."),
            ("{episodes}", "Episode count."),
            ("{qualities}", "Available resolutions."),
            ("{languages}", "Available audio tracks."),
            ("{genres}", "Comma-joined genre list."),
            ("{overview}", "Synopsis / overview."),
        ],
        "supports_html": True,
        "example": (
            "{title}『 #{tag} 』\n"
            "⌬ EPISODES : {episodes}\n"
            "⌬ QUALITY : {qualities}"
        ),
        "hint": (
            "Open the <b>NekoFetch admin bot → Settings → main_channel → "
            "caption_template</b> and send the full HTML template as one message."
        ),
        "danger": (
            "Only the placeholders listed above are substituted; an unknown "
            "<code>{token}</code> is left in the caption verbatim."
        ),
    },

    "main": {
        "title": "Main Channel",
        "about": (
            "Whether releases post to the public main channel and which "
            "channel receives them. Configured under <b>main_channel</b> in "
            "the NekoFetch admin Settings panel, alongside the Index and "
            "Download button labels."
        ),
        "when_to_use": (
            "When you set up (or move) the public main channel, or want to "
            "toggle main-channel posting off."
        ),
        "options": [
            ("main_channel.enabled", "Turn public main-channel posting on/off."),
            ("main_channel.channel_id", "Telegram id (-100…) of the channel."),
            ("main_channel.index_button_text", "Label of the Index button."),
            ("main_channel.download_button_text", "Label of the Download button."),
        ],
        "example": "main_channel.channel_id = -1001234567890",
        "hint": (
            "Open the <b>NekoFetch admin bot → Settings → main_channel</b> to "
            "change these; each field carries its own help panel."
        ),
        "danger": (
            "<b>channel_id</b> must reference a channel the userbot is an admin "
            "of, otherwise publishes silently fail."
        ),
    },

    "index": {
        "title": "Index Settings",
        "about": (
            "The stylized A-Z catalog index channel — whether it's enabled, "
            "which channel it posts to, and the templates for each letter "
            "header and catalog line. Configured under <b>index_channel</b> "
            "in the NekoFetch admin Settings panel."
        ),
        "when_to_use": (
            "When you set up the index channel, or want a different "
            "letter-header or per-title line style."
        ),
        "options": [
            ("index_channel.enabled", "Turn the index channel on/off."),
            ("index_channel.channel_id", "Telegram id (-100…) of the index channel."),
            ("index_channel.letter_header_template",
             "Header above each first-letter section ({letter}, {entries})."),
            ("index_channel.entry_template", "One catalog line per title ({title})."),
        ],
        "placeholders": [
            ("{letter}", "First-letter bucket (A, B, C …)."),
            ("{entries}", "Titles filed under that letter."),
            ("{title}", "Anime title (entry_template only)."),
        ],
        "supports_html": True,
        "example": "index_channel.entry_template = ⦿ {title}",
        "hint": (
            "Open the <b>NekoFetch admin bot → Settings → index_channel</b> to "
            "change these."
        ),
    },
}


ALL_BY_BOT = {
    "lelouch": LELOUCH,
    "levi": LEVI,
    "senku": SENKU,
    "gojo": GOJO,
}
