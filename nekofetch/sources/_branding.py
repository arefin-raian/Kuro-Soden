"""Shared brand-tag helpers for audio / subtitle track + container titles.

Single source of truth for the chrome-bracket title style that's used across
the new-download mux path (``_mux.py``), the manual re-mux path
(``_normalize.py``), the cross-source dual-audio path (``_dualaudio.py``),
and the on-screen subtitle cue in ``_subs.py``.

Visual style (kept consistent so MediaInfo / VLC / mpv all display the same
chrome-bracket label across every release):

  * Track name:    ``"Language〘 @AniXWeebs 〙"``
                   e.g. ``Japanese〘 @AniXWeebs 〙``
                   e.g. ``Anime Weebs #2〘 @AniXWeebs 〙`` (no language tag)

The corner brackets (U+3018 / U+3019) and the channel handle are the same
shape :class:`BrandingService` writes into captions and bot descriptions, so
the chrome feels uniform whether the user opens MediaInfo or reads a Telegram
post.

The terminal-level ``subtitle on-screen cue`` is unaffected by this module;
``_subs.py`` keeps its own text template for the ASS stream.
"""

from __future__ import annotations

# Channel handle. Kept in sync with the form used by ``_subs.py`` (ASS on-screen
# cue), ``_normalize.py`` (transmux path — historically identical), and the
# branding block in ``core/constants.py`` / ``services/bot_factory.py``.
BRAND_HANDLE = "@AniXWeebs"


def brand_track_title(name: str | None, ordinal: int) -> str:
    """Build a stylish track-name label: ``"Language〘 @AniXWeebs 〙"``.

    Args:
        name: the human display name (e.g. ``"Japanese"``, ``"Dual Audio"``).
            When ``None``/empty/whitespace-only, falls back to
            ``"Anime Weebs #N"`` for transparency — operators see the
            brand right next to a sequence number, so a duplicate or
            untagged track is obvious.
        ordinal: 1-based track position among its own stream type
            (audio+audio, audio+sub). Used only when the fallback fires.
    """
    base = name.strip() if name and name.strip() else f"Anime Weebs #{ordinal}"
    return f"{base}〘 {BRAND_HANDLE} 〙"


def brand_container_title(title: str) -> str:
    """Build a stylish container title: ``"AnimeName〢@AniXWeebs"``.

    Idempotent: if the title is ALREADY branded with our separator + handle,
    it's returned unchanged. This guards against double-branding when a
    caller already pre-branded (e.g. ``_normalize.py`` adds the brand
    itself before calling ``mux_to_mkv``).
    """
    marker = f"〢{BRAND_HANDLE}"
    if marker in title:
        return title
    return f"{title}{marker}"
