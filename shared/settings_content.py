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
            "Naming templates for new distribution channels, the footer text "
            "appended to every shared post, and the default sticker pack "
            "attached to each franchise's welcome message."
        ),
        "when_to_use": (
            "Whenever a new visual identity drops, or when an admin wants a "
            "footer that links the brand account."
        ),
        "options": [
            (
                "channelNameTemplate={title} ({year})",
                "Default — clean, year-prefixed for S1 indexing.",
            ),
            (
                "channelNameTemplate={title} ▸ {studio}",
                "Studio-aware variant for collaborations.",
            ),
            ("footerText=", "Disabled — no footer."),
            (
                "footerText=Join @KuroSoden for more!",
                "Default — drives follows at the bottom of every share.",
            ),
        ],
        "supports_html": True,
        "example": "/brand footerText=\"Sourced from Kuro Sōden ✦ kurosoden.example\"",
        "hint": (
            "Send one <code>key=\"value\"</code> pair at a time. Quoted values "
            "may include emoji and HTML tags if <code>supports_html</code> is on."
        ),
    },

    "layout": {
        "title": "Content Layout",
        "about": (
            "Visual style of every auto-generated artifact: info card, "
            "season separators, watch guide position, and footer emphasis. "
            "Tune so the channel feel matches the show's tone (e.g. SoL "
            "gets a softer separator, action shows get a banner)."
        ),
        "when_to_use": (
            "Before launching a new show, or after feedback that the channel "
            "feels too dense / too sparse."
        ),
        "options": [
            (
                "seasonSeparatorStyle=banner",
                "Default — wide banner with cover art.",
            ),
            (
                "seasonSeparatorStyle=card",
                "Square card — fits 1:1 thumbnails better.",
            ),
            (
                "seasonSeparatorStyle=line",
                "Minimal — single horizontal divider with the season name.",
            ),
            (
                "infoCardLayout=expanded",
                "Default — synopsis + metadata on the card.",
            ),
            (
                "infoCardLayout=compact",
                "Title + cover only; details in the comments.",
            ),
            (
                "watchGuidePosition=top",
                "Default — pinned at the top of the channel.",
            ),
            (
                "watchGuidePosition=sidebar",
                "Inline button in the info card.",
            ),
        ],
        "example": "/layout seasonSeparatorStyle=banner",
        "hint": (
            "Send one <code>key=value</code> at a time; the next artifact "
            "generated after this message uses the new layout."
        ),
    },
}


# ── gojo ──────────────────────────────────────────────────────────────────────

GOJO = {
    "caption": {
        "title": "Caption Template",
        "about": (
            "The Markdown/HTML template that wraps every Main Channel post. "
            "Use the placeholders listed below — they expand to the right "
            "value at publish time."
        ),
        "when_to_use": (
            "Whenever you want a consistent voice across all posts, or "
            "before a special event (e.g. anniversary caption)."
        ),
        "placeholders": [
            ("title", "Anime title (English when available, else original)."),
            ("code", "Request code — <code>REQ-XXXX</code>."),
            ("year", "Release year, e.g. <code>2024</code>."),
            ("genres", "Comma-joined list of genres."),
            ("score", "AniList score, e.g. <code>8.31</code>."),
            ("episodes", "Total episodes count."),
            ("studio", "Production studio."),
            ("duration", "Per-episode minutes."),
        ],
        "supports_html": True,
        "example": (
            "🎬 <b>${title}</b>  ·  <i>${year}</i>\n"
            "Genres: ${genres}\n"
            "AniList: ${score}  ·  ${episodes} episodes"
        ),
        "hint": (
            "Send the full Markdown/HTML template as a single message; "
            "$placeholders expand at publish time."
        ),
        "danger": (
            "Unknown placeholders will prevent automatic publishing — they "
            "land in the <b>log channel</b> as a failed job."
        ),
    },

    "main": {
        "title": "Main Channel",
        "about": (
            "Where approved releases land and how franchise entries are "
            "posted (single post vs. one per season)."
        ),
        "when_to_use": (
            "Every time the staff team adds a new main channel or wants to "
            "schedule posts for later."
        ),
        "options": [
            (
                "franchisePosting=per_season",
                "Default — one post per season, grouped under the same tag.",
            ),
            (
                "franchisePosting=per_anime",
                "Single franchise post linking every season.",
            ),
            (
                "scheduleWindow=immediate",
                "Default — publish as soon as approved.",
            ),
            (
                "scheduleWindow=4h",
                "Stagger posts every four hours.",
            ),
            (
                "scheduleWindow=daily_18:00",
                "Daily drop at 18:00 UTC.",
            ),
        ],
        "example": "/main routing_id=-1001234567890 scheduleWindow=4h",
        "hint": (
            "Send <code>/main routing_id=&lt;channel_id&gt; "
            "scheduleWindow=&lt;rule&gt;</code> with the new values."
        ),
        "danger": (
            "<b>routing_id</b> must reference a channel the publisher bot "
            "is a member of, otherwise publishes silently fail."
        ),
    },

    "index": {
        "title": "Index Settings",
        "about": (
            "How the A-Z index group is named, whether it refreshes on "
            "every publish, and the sort direction."
        ),
        "when_to_use": (
            "When the index gets crowded (switch to update_on_publish), "
            "or when you want a different letter-boundary style."
        ),
        "options": [
            ("updateOnPublish=true", "Default — keep the index live."),
            ("updateOnPublish=false", "Re-generate only on demand."),
            ("sortBy=title_asc", "Default — clean A-Z."),
            ("sortBy=date_desc", "Newest first; good for trending channels."),
            ("sortBy=score_desc", "Highest-rated first."),
        ],
        "example": "/index updateOnPublish=true sortBy=title_asc",
        "hint": "Send <code>/index key=value key=value ...</code>.",
    },
}


ALL_BY_BOT = {
    "lelouch": LELOUCH,
    "levi": LEVI,
    "senku": SENKU,
    "gojo": GOJO,
}
