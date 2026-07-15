"""Distribution-bot display-name formatting.

A per-title bot's name encodes, at a glance, what it carries:

    "<Title>『 <audio type> 』« <languages> » <qualities>"

The audio type is derived from which audio tracks actually exist:

    * dual audio (one file, both tracks) → "Dual Audio"
    * separate sub + dub files           → "Sub & Dub"
    * dub only                           → "Dub"
    * sub only                           → "Sub"

Telegram caps a bot name at 64 chars, so the title half is truncated to fit while
the tag is always preserved (the tag is the part users scan for).
"""

from __future__ import annotations

from nekofetch.domain.enums import AudioType

_BOT_NAME_LIMIT = 64


def audio_tag(audios: set) -> str:
    """The audio-type label for a set of available audio tracks.

    Distinguishes genuine Dual Audio (both languages in one file) from
    separate Sub + Dub files — "Dual" only appears when a DUAL_AUDIO
    file exists."""
    vals = {a.value if isinstance(a, AudioType) else str(a) for a in audios}
    has_dual = AudioType.DUAL_AUDIO.value in vals
    has_sub = AudioType.SUBBED.value in vals
    has_dub = AudioType.DUBBED.value in vals
    multi = AudioType.MULTI.value in vals

    if multi:
        return "Multi Audio"
    if has_dual:
        return "Dual Audio"
    if has_sub and has_dub:
        return "Sub & Dub"
    if has_dub:
        return "Dub"
    if has_sub:
        return "Sub"
    return ""


def language_label(languages: set | None) -> str:
    """Human-readable language list: 'Japanese & English', 'Japanese', etc.

    Recognises BOTH the canonical full names (``"english"``, ``"japanese"``)
    AND the 2-letter ISO codes (``"en"``, ``"ja"``) so callers using either
    form get the same canonical word on the bot name AND inside the season
    card. Without both keys, one surface would render ``"English & Japanese"``
    and the other ``"En & Ja"`` — the exact drift the alignment pass set
    out to eliminate.
    """
    langs = sorted({l.strip().lower() for l in (languages or set()) if l and l.strip()})
    if not langs:
        return ""
    names = {
        # Full names — canonical, fed in by bot_factory._gather.
        "japanese": "Japanese", "english": "English", "hindi": "Hindi",
        "korean":  "Korean",  "chinese": "Chinese", "spanish": "Spanish",
        # 2-letter ISO codes — also recognised; feeding "en" / "ja" / "hi"
        # otherwise produces "En, Hi & Ja".
        "ja": "Japanese", "en": "English", "hi": "Hindi",
        "ko": "Korean", "zh": "Chinese", "es": "Spanish",
    }
    labelled = [names.get(l, l.title()) for l in langs]
    if len(labelled) == 1:
        return labelled[0]
    return " & ".join([", ".join(labelled[:-1]), labelled[-1]])


def format_bot_name(
    english: str | None, romaji: str | None, *,
    audios: set, languages: set | None = None,
    qualities: list[str] | None = None, limit: int = _BOT_NAME_LIMIT,
) -> str:
    """Build the bot's display name:
    '<Title>『 <audio> 』« <languages> » <qualities>', fit to ``limit``."""
    english = (english or "").strip()
    romaji = (romaji or "").strip()
    title = english or romaji or "Anime"

    tag = audio_tag(audios)
    langs = language_label(languages)
    quals = " ".join(qualities) if qualities else ""

    suffix_parts = []
    if tag:
        suffix_parts.append(f"『 {tag} 』")
    if langs:
        suffix_parts.append(f"« {langs} »")
    if quals:
        suffix_parts.append(quals)
    suffix = " ".join(suffix_parts)

    if not suffix:
        return title[:limit]

    # Preserve the suffix; truncate the title half to fit the 64-char limit.
    room = limit - len(suffix) - 1  # -1 for the space between title and suffix
    if len(title) > room and room > 3:
        title = title[: max(0, room - 1)].rstrip() + "…"
    return f"{title} {suffix}"[:limit]


def format_bot_username(
    base: str, anime_doc_id: str, *,
    suffix: str | None = None,
    is_channel: bool = False,
) -> str:
    """A valid, reasonably-unique bot/channel username candidate (5–32 chars).

    Telegram requires bot usernames to end in 'bot'; channel usernames do not.
    Set ``is_channel=True`` to drop the 'bot' suffix (channels use e.g. ``_axw``).
    When ``suffix`` is None, the default from ``BotConfig`` is used.
    """
    import re

    if suffix is None:
        from nekofetch.core.config import get_app_config
        cfg = get_app_config().bot
        suffix = cfg.channel_username_suffix if is_channel else cfg.bot_username_suffix

    slug = re.sub(r"[^a-z0-9]+", "_", (base or "anime").lower()).strip("_")
    # leave room for the "_<suffix>" tail (and "_bot" if applicable) within 32 chars
    tail = f"_{suffix}"
    if not is_channel:
        tail += "_bot"
    slug = slug[: max(1, 32 - len(tail))].strip("_") or "anime"
    name = f"{slug}{tail}"
    return name[:32]
