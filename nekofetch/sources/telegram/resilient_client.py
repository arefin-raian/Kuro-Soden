"""Resilient metadata client — tries AniList first, falls back to MyAnimeList.

Every public method mirrors ``AnilistClient``'s signature and return types.
On connection failures, HTTP errors, or when AniList returns ``None``
(notably a 403 when AniList is down), the call is transparently retried
against the MyAnimeList (Jikan) fallback.

Usage from container::

    self.anilist = ResilientMetadataClient()

Every caller that previously did ``await container.anilist.search(…)`` or
``await container.anilist.walk_franchise_full(…)`` continues to work without
modification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nekofetch.core.logging import get_logger
from nekofetch.sources.telegram.anilist import AnilistClient
from nekofetch.sources.telegram.myanimelist import MyAnimeListClient

if TYPE_CHECKING:
    from nekofetch.sources.telegram.anilist import (
        AnilistMedia,
        FranchiseEntry,
        FranchiseTotals,
    )

log = get_logger(__name__)


class ResilientMetadataClient:
    """Drop-in replacement for ``AnilistClient`` with automatic MAL fallback.

    Every method tries AniList first.  If AniList raises an exception or
    returns ``None`` (e.g. HTTP 403 — \"temporarily disabled\"), the call
    is transparently retried against MyAnimeList via the Jikan REST API.
    """

    def __init__(self) -> None:
        self.anilist = AnilistClient()
        self.mal = MyAnimeListClient()

    async def close(self) -> None:
        await self.anilist.close()
        await self.mal.close()

    # ── core fallback logic ───────────────────────────────────────────────────

    @staticmethod
    async def _try_both(
        primary_method, fallback_method, *args, **kwargs
    ):
        """Call ``primary_method``; on ``None`` or exception, call ``fallback_method``."""
        try:
            result = await primary_method(*args, **kwargs)
            if result is not None:
                return result
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "anilist.fallback",
                method=getattr(primary_method, "__name__", str(primary_method)),
                error=str(exc)[:200],
            )
        # Fallback
        try:
            return await fallback_method(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "mal.fallback.failed",
                method=getattr(fallback_method, "__name__", str(fallback_method)),
                error=str(exc)[:200],
            )
            return None

    # ── public API ────────────────────────────────────────────────────────────

    async def search(self, query: str) -> "AnilistMedia | None":
        return await self._try_both(
            self.anilist.search, self.mal.search, query
        )

    async def _fetch_full(self, media_id: int) -> "AnilistMedia | None":
        """Fetch full media data by ID.

        When ``media_id`` is a MAL ID (returned by a previous MAL ``search``)
        and AniList is unreachable, the call correctly falls through to MAL.
        If AniList is reachable but ``media_id`` doesn't exist on AniList,
        the result is ``None`` — the MAL fallback then handles it.
        """
        return await self._try_both(
            self.anilist._fetch_full, self.mal._fetch_full, media_id
        )

    async def franchise_totals(
        self, root_id: int, *, max_nodes: int = 120
    ) -> "FranchiseTotals":
        result = await self._try_both(
            self.anilist.franchise_totals,
            self.mal.franchise_totals,
            root_id,
            max_nodes=max_nodes,
        )
        # _try_both returns None on total failure, but both clients always
        # return FranchiseTotals (never None).  We fall back to empty totals.
        from nekofetch.sources.telegram.anilist import FranchiseTotals as FT

        return result if result is not None else FT()

    async def walk_franchise_full(
        self, root_id: int, *, max_nodes: int = 120
    ) -> "dict[int, FranchiseEntry]":
        result = await self._try_both(
            self.anilist.walk_franchise_full,
            self.mal.walk_franchise_full,
            root_id,
            max_nodes=max_nodes,
        )
        return result if result is not None else {}

    async def title_variants(self, query: str) -> "list[str]":
        result = await self._try_both(
            self.anilist.title_variants, self.mal.title_variants, query
        )
        return result if result is not None else [query]
