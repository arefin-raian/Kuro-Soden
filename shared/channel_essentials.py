"""The channel-creation essentials Senku hands the admin, verbatim from NekoFetch.

NekoFetch's auto-pipeline builds a distribution channel's **title**, **username**,
and **description** from one place: ``BotFactory`` (via ``_gather`` +
``format_bot_name`` / ``format_bot_username``) and its ``_BRANDING_DESCRIPTION``
block. Kuro Sōden is the *manual* version of that same pipeline, so Senku must
surface the identical values for the admin to paste — not a re-derivation that can
drift. This module is the single adapter: it calls the exact NekoFetch functions
and returns their output as a small dataclass.

Nothing here talks to Telegram; it only reads Postgres (storage packs) + config.
Every field is best-effort — a title with no stored packs still yields a usable
name from the franchise's English/romaji, just without the audio/quality suffix.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

log = get_logger(__name__)

_TMDB_SEARCH = "https://www.themoviedb.org/search?query={q}"


@dataclass(slots=True)
class ChannelEssentials:
    """The paste-ready pieces for creating one distribution channel."""

    title: str                 # display name — paste as the channel title
    username: str              # suggested @username (no leading @)
    description: str           # channel bio / description block
    poster_search_url: str     # TMDB poster page to open (never auto-copied)


async def build_channel_essentials(
    container: Container, *, anime_doc_id: str | None, franchise: dict | None,
) -> ChannelEssentials:
    """Assemble the channel-creation essentials for a title.

    Reuses :class:`BotFactory` so the manual output matches what the auto-pipeline
    would have produced: ``_gather`` pulls the real audio/language/quality from the
    storage packs, ``format_bot_name`` composes the display name, and
    ``format_bot_username(is_channel=True)`` yields the ``…_axw`` channel handle.
    The description is NekoFetch's configured branding block (operator override or
    the built-in AniXWeebs network block).
    """
    from nekofetch.services.bot_factory import BotFactory
    from nekofetch.services.bot_naming import format_bot_name, format_bot_username

    franchise = franchise or {}
    english = (franchise.get("english") or franchise.get("title") or "").strip()
    romaji = (franchise.get("romaji") or "").strip()

    meta: dict = {}
    if anime_doc_id:
        try:
            # The one place NekoFetch resolves name ingredients from real packs.
            meta = await BotFactory(container)._gather(anime_doc_id)
        except Exception as exc:  # noqa: BLE001 — packs may be absent pre-store
            log.warning("channel_essentials.gather_failed",
                        anime=anime_doc_id, error=str(exc))

    # Prefer the franchise's titles when _gather couldn't resolve them.
    english = (meta.get("english") or "").strip() or english
    romaji = (meta.get("romaji") or "").strip() or romaji
    base_title = english or romaji or (anime_doc_id or "Anime")

    title = format_bot_name(
        english or base_title, romaji,
        audios=meta.get("audios") or set(),
        languages=meta.get("languages"),
        qualities=meta.get("qualities"),
    )
    username = format_bot_username(base_title, anime_doc_id or "", is_channel=True)
    description = _description(container)
    poster_url = _TMDB_SEARCH.format(q=quote_plus(base_title))

    return ChannelEssentials(
        title=title, username=username,
        description=description, poster_search_url=poster_url,
    )


def _description(container: Container) -> str:
    """The channel description — operator override or NekoFetch's branding block.

    Mirrors ``BotFactory._build_description`` but WITHOUT prepending a per-title
    line: a channel bio is the same network block on every channel (the admin's
    instruction is 'paste it exactly, same for every title'). Falls back to the
    literal branding block if config can't be read.
    """
    from nekofetch.services.bot_factory import BotFactory

    try:
        override = (getattr(container.config.bot, "description_text", "") or "").strip()
    except Exception:  # noqa: BLE001 — config shape guard
        override = ""
    if override:
        return override[:512]
    return BotFactory._BRANDING_DESCRIPTION[:512]
