"""Project-wide constant values.

The design language is *terminal-clean, anime-modern*: a small, cohesive set of
Unicode marks that read well in Telegram's monospace-ish rendering. One palette,
used everywhere, so the whole surface feels like one product. Prefer the
semantic names below (``DOT_ACTIVE``, ``RULE``, ``ARROW``) over raw characters.
"""

from __future__ import annotations

# ── Rules / dividers ──────────────────────────────────────────────────────────
# Kept short (≈12 cells) so they never wrap to a second line on a narrow phone.
RULE = "────────────"          # primary section divider (thin)
RULE_SOFT = "╌╌╌╌╌╌╌╌╌╌╌╌"      # secondary / sub-divider
RULE_HEAVY = "━━━━━━━━━━━━"      # header underline / emphasis

# ── Progress bar cells ────────────────────────────────────────────────────────
BAR_FILLED = "█"
BAR_EMPTY = "░"

# ── Status dots (lifecycle / health) ──────────────────────────────────────────
DOT_DONE = "●"        # completed
DOT_ACTIVE = "◐"      # in progress
DOT_PENDING = "○"     # waiting
DOT_FAIL = "✕"        # failed / blocked

# ── Structure / pointers ──────────────────────────────────────────────────────
ARROW = "→"
CHEVRON = "›"
TRIANGLE = "▸"
BULLET = "•"
TREE_MID = "├─"
TREE_END = "╰─"
PIPE = "│"
PIPE_DOTTED = "┆"

# ── Legacy aliases (kept so older imports keep resolving; migrate to the
# semantic names above). ──
DIAMOND_FILLED = TRIANGLE
DIAMOND_HOLLOW = "◦"
DIAMOND_FANCY = "◆"

# ── Redis key namespaces ──
REDIS_PROGRESS = "nf:progress:{job_id}"
REDIS_RATELIMIT = "nf:rl:{user_id}"
REDIS_FSM = "nf:fsm:{bot}:{user_id}"
REDIS_JOB_LOCK = "nf:lock:{job_id}"
# Channel-scoped awaited-reply marker. Anonymous admins post as the channel
# (no ``from_user``), so a per-user FSM key can't be built — a reply-expecting
# channel flow arms this by chat id instead. See ``bots.channel_reply``.
REDIS_CHANNEL_REPLY = "nf:chanreply:{chat_id}"

# ── Request identifiers ──
REQUEST_PREFIX = "REQ"

# ── Reply-expecting FSM states ──
# When the on-duty admin is in one of these states, the control-center channel
# guard must NOT auto-delete their next text message on arrival — that message
# IS the awaited reply (an AniZone slug list, a franchise edit, a custom
# resolution). The consuming handler deletes it itself once it's been read, so
# the channel still ends up clean. See ``channel_guard`` and ``review`` handlers.
REPLY_EXPECTING_STATES = frozenset({
    "staff:anizone:slugs",       # STATE_ANIZONE_SLUGS
    "staff:franchise:edit",      # STATE_FRANCHISE_EDIT
    "staff:manual:custom_res",   # STATE_MANUAL_CUSTOM_RES
})

# ── Pagination ──
DEFAULT_PAGE_SIZE = 8
