"""TMDB logo and image asset fetching — logos, posters, backdrops for thumbnails.

Extends the base ``TmdbClient`` with methods that fetch **logos** (title art /
branding) from TMDB's ``/images`` endpoint, plus helpers for ranking all asset
types by quality.

Logos are fetched with ``include_image_language=en,null`` so English-title
artwork comes first, then language-neutral, ranked by vote count and resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nekofetch.core.logging import get_logger

if TYPE_CHECKING:
    from nekofetch.providers.metadata.tmdb import TmdbClient

log = get_logger(__name__)

IMG_BASE = "https://image.tmdb.org/t/p"


def _quality_key(item: dict) -> tuple:
    """Sort key for TMDB image assets: rating, vote count, then resolution."""
    return (
        item.get("vote_average") or 0,
        item.get("vote_count") or 0,
        item.get("width") or 0,
    )


async def fetch_logos(client: "TmdbClient", tmdb_id: int, media_type: str) -> list[dict]:
    """Fetch ranked logo images from TMDB.

    Returns a list of dicts sorted by quality (best first):
    ``{"url": str, "file_path": str, "language": str | None, "width": int,
        "height": int, "vote_average": float, "vote_count": int}``

    English-tagged logos come first, then language-neutral, then others.
    """
    try:
        imgs = await client._get(
            f"/{media_type}/{tmdb_id}/images",
            include_image_language="en,null",
        )
    except Exception as exc:
        log.warning("tmdb.logos.failed", id=tmdb_id, error=str(exc))
        return []

    logos = imgs.get("logos", [])
    if not logos:
        return []

    # Sort: English first, then neutral, then others; within each tier by quality
    def sort_key(l: dict) -> tuple:
        lang = l.get("iso_639_1") or ""
        tier = 0 if lang == "en" else (1 if lang == "" else 2)
        return (tier, -l.get("vote_count", 0), -_quality_key(l)[2])

    logos.sort(key=sort_key)

    return [
        {
            "url": f"{IMG_BASE}/original{l['file_path']}",
            "file_path": l["file_path"],
            "language": l.get("iso_639_1"),
            "width": l.get("width", 0),
            "height": l.get("height", 0),
            "vote_average": l.get("vote_average", 0),
            "vote_count": l.get("vote_count", 0),
        }
        for l in logos
    ]


async def fetch_posters_ranked(
    client: "TmdbClient", tmdb_id: int, media_type: str,
) -> list[dict]:
    """Fetch ranked poster images from TMDB (English first, then neutral).

    Returns same format as ``fetch_logos`` but with ``w500`` sized URLs.
    """
    try:
        imgs = await client._get(
            f"/{media_type}/{tmdb_id}/images",
            include_image_language="en,null",
        )
    except Exception as exc:
        log.warning("tmdb.posters.failed", id=tmdb_id, error=str(exc))
        return []

    posters = imgs.get("posters", [])
    if not posters:
        return []

    def sort_key(p: dict) -> tuple:
        lang = p.get("iso_639_1") or ""
        tier = 0 if lang == "en" else (1 if lang == "" else 2)
        return (tier, -p.get("vote_count", 0), -_quality_key(p)[2])

    posters.sort(key=sort_key)

    return [
        {
            "url": f"{IMG_BASE}/w500{p['file_path']}",
            "file_path": p["file_path"],
            "language": p.get("iso_639_1"),
            "width": p.get("width", 0),
            "height": p.get("height", 0),
            "vote_average": p.get("vote_average", 0),
            "vote_count": p.get("vote_count", 0),
        }
        for p in posters
    ]


async def fetch_backdrops_ranked(
    client: "TmdbClient", tmdb_id: int, media_type: str,
) -> list[dict]:
    """Fetch **textless** backdrop images for the thumbnail-generator picker.

    The thumbnail bot overlays the user's chosen logo on top, so the backdrop
    options offered MUST be textless — the ``?image_language=xx`` (no-language)
    gallery, art with no title baked in. We request only ``null`` from TMDB and
    additionally guard in-code against any language-tagged art slipping through.
    This is the opposite of the confirmation card, which wants English-tagged
    art (see ``TmdbClient._confirm_backdrop``).

    Returns same format as ``fetch_logos`` but with ``w1280`` sized URLs.
    """
    try:
        imgs = await client._get(
            f"/{media_type}/{tmdb_id}/images",
            include_image_language="null",
        )
    except Exception as exc:
        log.warning("tmdb.backdrops.failed", id=tmdb_id, error=str(exc))
        return []

    # Textless only: drop anything carrying a language tag (baked-in title text).
    backdrops = [b for b in imgs.get("backdrops", []) if not b.get("iso_639_1")]
    if not backdrops:
        return []

    def sort_key(b: dict) -> tuple:
        return (-b.get("vote_count", 0), -_quality_key(b)[2])

    backdrops.sort(key=sort_key)

    return [
        {
            "url": f"{IMG_BASE}/w1280{b['file_path']}",
            "file_path": b["file_path"],
            "language": b.get("iso_639_1"),
            "width": b.get("width", 0),
            "height": b.get("height", 0),
            "vote_average": b.get("vote_average", 0),
            "vote_count": b.get("vote_count", 0),
        }
        for b in backdrops
    ]
