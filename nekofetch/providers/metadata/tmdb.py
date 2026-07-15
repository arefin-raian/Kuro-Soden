"""TMDB client — backdrops + display metadata for the search-confirm UI.

Given an anime title we fetch the best TMDB match (TV first, then movie), its
display info, and an English promotional backdrop (16:9) for the confirmation
card. Auth uses the v4 read access token (Bearer); falls back to the v3 api_key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from nekofetch.core.logging import get_logger

log = get_logger(__name__)

TMDB_API = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p"


@dataclass
class TmdbResult:
    id: int
    media_type: str           # "tv" | "movie"
    title: str
    year: str | None
    genres: list[str] = field(default_factory=list)
    rating: float | None = None
    overview: str = ""
    seasons: int | None = None
    episodes: int | None = None
    backdrop_url: str | None = None     # English 16:9 backdrop (original size)
    poster_url: str | None = None
    native_title: str = ""              # original_name/title (e.g. Japanese)
    logo_url: str | None = None         # transparent title-art PNG (enrich=True)
    runtime: int | None = None          # minutes (episode run time for TV)
    director: str = ""                  # enrich=True
    certification: str = ""             # e.g. "PG-13" / "TV-14" (enrich=True)

    def backdrop(self, size: str = "w1280") -> str | None:
        if not self._backdrop_path:
            return self.backdrop_url
        return f"{IMG_BASE}/{size}{self._backdrop_path}"

    _backdrop_path: str | None = None


class TmdbClient:
    def __init__(self, token: str | None = None, api_key: str | None = None) -> None:
        self.token = token or os.getenv("TMDB_API_READ_ACCESS_TOKEN", "")
        self.api_key = api_key or os.getenv("TMDB_API_KEY", "")
        self._http: httpx.AsyncClient | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            headers = {"accept": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._http = httpx.AsyncClient(timeout=20.0, headers=headers)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _params(self, **extra) -> dict:
        p = dict(extra)
        if not self.token and self.api_key:  # v3 key fallback
            p["api_key"] = self.api_key
        return p

    async def _get(self, path: str, **params) -> dict:
        r = await self.http.get(f"{TMDB_API}{path}", params=self._params(**params))
        r.raise_for_status()
        return r.json()

    async def search(self, title: str, *, enrich: bool = False) -> TmdbResult | None:
        """Best match for ``title`` — prefers TV, then movie, by popularity.

        ``enrich=True`` also pulls the title logo, runtime, director and content
        certification (2 extra API calls) — used by the thumbnail composer.
        """
        candidates: list[dict] = []
        try:
            for media in ("tv", "movie"):
                data = await self._get(f"/search/{media}", query=title,
                                       include_adult="false", language="en-US")
                for item in data.get("results", [])[:5]:
                    item["_media"] = media
                    candidates.append(item)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("tmdb.search.failed", title=title, error=str(exc))
            return None
        if not candidates:
            return None
        # prefer TV, then higher popularity
        candidates.sort(key=lambda c: (c["_media"] == "tv", c.get("popularity", 0)),
                        reverse=True)
        top = candidates[0]
        return await self.details(top["id"], top["_media"], enrich=enrich)

    async def details(self, tmdb_id: int, media_type: str,
                      *, enrich: bool = False) -> TmdbResult | None:
        is_tv = media_type == "tv"
        try:
            # One call pulls base fields + (when enriching) credits + certification.
            append = "credits,release_dates,content_ratings" if enrich else ""
            d = await self._get(f"/{media_type}/{tmdb_id}", language="en-US",
                                **({"append_to_response": append} if append else {}))
            backdrop_path = await self._english_backdrop(tmdb_id, media_type) \
                or d.get("backdrop_path")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("tmdb.details.failed", id=tmdb_id, error=str(exc))
            return None

        title = d.get("name") if is_tv else d.get("title")
        date = d.get("first_air_date") if is_tv else d.get("release_date")
        runtime = None
        if is_tv:
            ert = d.get("episode_run_time") or []
            runtime = int(ert[0]) if ert else None
        elif d.get("runtime"):
            runtime = int(d["runtime"])
        res = TmdbResult(
            id=tmdb_id, media_type=media_type, title=title or "",
            year=(date or "")[:4] or None,
            genres=[g["name"] for g in d.get("genres", [])],
            rating=round(d["vote_average"], 1) if d.get("vote_average") else None,
            overview=d.get("overview", "") or "",
            seasons=d.get("number_of_seasons") if is_tv else None,
            episodes=d.get("number_of_episodes") if is_tv else None,
            poster_url=f"{IMG_BASE}/w500{d['poster_path']}" if d.get("poster_path") else None,
            native_title=(d.get("original_name") if is_tv else d.get("original_title")) or "",
            runtime=runtime,
        )
        res._backdrop_path = backdrop_path
        res.backdrop_url = res.backdrop("original")
        if enrich:
            res.logo_url = await self._english_logo(tmdb_id, media_type)
            res.director = self._extract_director(d, is_tv)
            res.certification = self._extract_certification(d, is_tv)
        return res

    @staticmethod
    def _extract_director(d: dict, is_tv: bool) -> str:
        # TV: prefer the creator; fall back to a crew Director. Movie: crew Director.
        if is_tv:
            creators = d.get("created_by") or []
            if creators:
                return creators[0].get("name", "") or ""
        crew = (d.get("credits") or {}).get("crew") or []
        directors = [c.get("name", "") for c in crew
                     if c.get("job") in ("Director", "Series Director")]
        return directors[0] if directors else ""

    @staticmethod
    def _extract_certification(d: dict, is_tv: bool) -> str:
        try:
            if is_tv:
                for r in (d.get("content_ratings") or {}).get("results", []):
                    if r.get("iso_3166_1") == "US" and r.get("rating"):
                        return r["rating"]
            else:
                for r in (d.get("release_dates") or {}).get("results", []):
                    if r.get("iso_3166_1") == "US":
                        for rd in r.get("release_dates", []):
                            if rd.get("certification"):
                                return rd["certification"]
        except (AttributeError, TypeError, KeyError):
            pass
        return ""

    async def _english_logo(self, tmdb_id: int, media_type: str) -> str | None:
        """Best English (then neutral) transparent title-art logo, PNG preferred."""
        try:
            imgs = await self._get(f"/{media_type}/{tmdb_id}/images",
                                   include_image_language="en,null")
        except (httpx.HTTPError, ValueError):
            return None
        logos = imgs.get("logos", [])
        if not logos:
            return None

        def quality(b: dict) -> tuple:
            # Prefer PNG (transparent) over SVG, then higher rating/votes/width.
            return (b.get("file_path", "").lower().endswith(".png"),
                    b.get("vote_average") or 0, b.get("vote_count") or 0,
                    b.get("width") or 0)

        english = sorted((b for b in logos if b.get("iso_639_1") == "en"),
                         key=quality, reverse=True)
        pool = english or sorted((b for b in logos if not b.get("iso_639_1")),
                                 key=quality, reverse=True) or sorted(logos, key=quality, reverse=True)
        path = pool[0].get("file_path") if pool else None
        return f"{IMG_BASE}/w500{path}" if path else None

    async def _english_backdrop(self, tmdb_id: int, media_type: str) -> str | None:
        """Pick the best **English-tagged** backdrop, the way TMDB's
        ``/images/backdrops?image_language=en`` page shows them.

        These are the franchise backdrops that carry English title art / branding,
        which we want on the confirmation card. Strict preference order:

          1. images explicitly tagged ``iso_639_1 == "en"`` (highest quality first),
          2. language-neutral images (``null``) as a graceful fallback,
          3. anything else only as a last resort.

        Within each tier we rank by rating, then vote count, then resolution, so a
        zero-vote English backdrop still beats a popular neutral one.
        """
        try:
            imgs = await self._get(f"/{media_type}/{tmdb_id}/images",
                                   include_image_language="en,null")
        except (httpx.HTTPError, ValueError):
            return None
        backdrops = imgs.get("backdrops", [])
        if not backdrops:
            return None

        def quality(b: dict) -> tuple:
            return (b.get("vote_average") or 0,
                    b.get("vote_count") or 0,
                    b.get("width") or 0)

        english = sorted((b for b in backdrops if b.get("iso_639_1") == "en"),
                         key=quality, reverse=True)
        if english:
            return english[0].get("file_path")
        neutral = sorted((b for b in backdrops if not b.get("iso_639_1")),
                         key=quality, reverse=True)
        if neutral:
            return neutral[0].get("file_path")
        return sorted(backdrops, key=quality, reverse=True)[0].get("file_path")

    async def _ranked_posters(self, tmdb_id: int, media_type: str) -> list[str]:
        """English/region-neutral poster paths, best-first — the same set TMDB's
        ``/images/posters?image_language=en&image_region=US`` page shows. English
        title-art posters first, then language-neutral, ranked by rating/votes/res."""
        try:
            imgs = await self._get(f"/{media_type}/{tmdb_id}/images",
                                   include_image_language="en,null")
        except (httpx.HTTPError, ValueError):
            return []
        posters = imgs.get("posters", [])

        def quality(b: dict) -> tuple:
            return (b.get("vote_average") or 0, b.get("vote_count") or 0, b.get("width") or 0)

        english = sorted((b for b in posters if b.get("iso_639_1") == "en"),
                         key=quality, reverse=True)
        neutral = sorted((b for b in posters if not b.get("iso_639_1")),
                         key=quality, reverse=True)
        seen: set = set()
        out: list[str] = []
        for b in (*english, *neutral):
            path = b.get("file_path")
            if path and path not in seen:
                seen.add(path)
                out.append(path)
        return out

    async def _english_poster(self, tmdb_id: int, media_type: str) -> str | None:
        ranked = await self._ranked_posters(tmdb_id, media_type)
        return ranked[0] if ranked else None

    async def poster_for(self, title: str, *, size: str = "w342", rank: int = 0) -> str | None:
        """Official English/US poster URL for ``title``, sized for the use site.

        ``rank=0`` is the best poster (used for file thumbnails); ``rank=1`` returns
        a DIFFERENT poster (used for a bot's profile photo) so the avatar isn't a
        carbon copy of the file thumbnails. Falls back to the best available."""
        res = await self.search(title)
        if res is None:
            return None
        ranked = await self._ranked_posters(res.id, res.media_type)
        if ranked:
            path = ranked[rank] if rank < len(ranked) else ranked[0]
            return f"{IMG_BASE}/{size}{path}"
        return res.poster_url
