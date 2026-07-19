"""Update check service — discover new franchise entries via AniList and create requests.

Runs on a monthly schedule or on demand via the ``/checkupdates`` admin command.

For each published anime (has a ``ChannelPost`` row), the service:

  1. Walks the FULL franchise graph via ``AnilistClient.walk_franchise_full``
  2. Compares discovered entries against existing ``StoragePack`` rows
  3. Any TV-season entry without a matching storage pack is considered **new**
  4. Creates an auto-request for each new entry so it goes through the normal
     pipeline (source assignment → download → process → storage → publish)

After the new entry is processed and published, the distribution bot/channel
is automatically updated because ``PublishingService.publish`` calls
``BotOrchestratorService.ensure_bot_for_anime`` which regenerates all content
posts (bumping ``content_revision`` so returning users get the updated set).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from nekofetch.core.container import Container
from nekofetch.core.exceptions import NotFound
from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import DownloadScope
from nekofetch.infrastructure.database.postgres.models import (
    ChannelPost,
    Request,
    StoragePack,
)
from nekofetch.infrastructure.database.postgres.session import session_scope

log = get_logger(__name__)

# TV formats that get sequential season numbers.
_TV_FORMATS = {"TV", "TV_SHORT", "TV_SPECIAL"}
# Extra formats that appear in the franchise.
_EXTRA_FORMATS = {"OVA", "ONA", "MOVIE", "SPECIAL"}
# All anime formats we care about.
_ANIME_FORMATS = _TV_FORMATS | _EXTRA_FORMATS


@dataclass
class NewEntry:
    """A franchise entry that was discovered during an update check."""

    anilist_id: int
    format: str
    english_title: str
    season_number: int | None  # None for extras (OVA/MOVIE/SPECIAL)
    episode_count: int | None
    relation: str = ""


@dataclass
class CheckResult:
    """Result of a single anime's update check."""

    anime_doc_id: str
    title: str
    new_entries: list[NewEntry] = field(default_factory=list)
    total_entries: int = 0
    error: str | None = None


class UpdateCheckService:
    """Discover new franchise entries and create requests for them."""

    def __init__(self, container: Container) -> None:
        self._c = container

    async def check_all(self, *, create: bool = True) -> list[CheckResult]:
        """Check EVERY published anime for new franchise entries.

        Returns a list of ``CheckResult``, one per anime. Only results with
        ``new_entries`` are actionable; the rest are informational.

        ``create=False`` runs a **detect-only** sweep — no requests are created,
        so a Gojo admin can review/trim the list first (edit-before-submit) and
        commit later via :meth:`create_requests_for`.
        """
        anime_list = await self._list_published_anime()
        results: list[CheckResult] = []
        for anime_doc_id, title in anime_list:
            try:
                result = await self.check_for_anime(anime_doc_id, title, create=create)
                results.append(result)
                if result.new_entries:
                    log.info(
                        "update_check.found",
                        anime=anime_doc_id,
                        new=len(result.new_entries),
                        total=result.total_entries,
                    )
            except Exception as exc:  # noqa: BLE001 - one failure never blocks the sweep
                log.warning(
                    "update_check.failed",
                    anime=anime_doc_id,
                    error=str(exc),
                )
                results.append(
                    CheckResult(
                        anime_doc_id=anime_doc_id,
                        title=title,
                        error=str(exc),
                    )
                )
        log.info("update_check.done", checked=len(results))
        return results

    async def check_for_anime(
        self, anime_doc_id: str, title: str | None = None, *, create: bool = True
    ) -> CheckResult:
        """Check a single anime for new franchise entries.

        Walks the franchise graph, compares against existing storage packs,
        and (when ``create``) creates requests for any new entries found. Pass
        ``create=False`` for a detect-only pass that leaves the queue untouched.
        """
        if title is None:
            title = anime_doc_id

        # Resolve the root AniList ID from an existing request.
        root_id = await self._resolve_anilist_id(anime_doc_id)
        if root_id is None:
            return CheckResult(
                anime_doc_id=anime_doc_id,
                title=title,
                error="Could not resolve AniList ID from existing requests",
            )

        # Walk the full franchise graph.
        entries = await self._c.anilist.walk_franchise_full(root_id)
        if not entries:
            return CheckResult(
                anime_doc_id=anime_doc_id,
                title=title,
                error="Franchise walk returned no entries",
            )

        # Get existing storage packs for comparison.
        existing_seasons = await self._get_existing_seasons(anime_doc_id)
        # Get existing entry_ids for extras (packs with season=None that have entry_id set).
        existing_entry_ids = await self._get_existing_entry_ids(anime_doc_id)

        # Sort TV entries chronologically.
        tv_entries = sorted(
            [e for e in entries.values() if e.format in _TV_FORMATS],
            key=lambda e: (
                (e.start_date or {}).get("year", 9999),
                (e.start_date or {}).get("month", 99),
                (e.start_date or {}).get("day", 99),
            ),
        )
        # Collect extras.
        extra_entries = [
            e for e in entries.values()
            if e.format in _EXTRA_FORMATS
        ]

        # Detect new TV entries: an entry at index i corresponds to season (i+1).
        # If that season number isn't in existing_seasons, it's new.
        new_entries: list[NewEntry] = []
        for i, entry in enumerate(tv_entries):
            season_num = i + 1
            if season_num not in existing_seasons:
                new_entries.append(
                    NewEntry(
                        anilist_id=entry.anilist_id,
                        format=entry.format,
                        english_title=entry.english_title,
                        season_number=season_num,
                        episode_count=entry.episodes,
                        relation=entry.relation,
                    )
                )

        # Detect new extras (MOVIE/OVA/ONA/SPECIAL) by comparing against existing
        # entry_ids from storage packs. walk_franchise_full already excludes SUMMARY
        # relation type (compilations/recaps) via _CONTENT_WALK_RELS, so only canon
        # extras appear here.
        #
        # Safety: if legacy extras exist (packs with season=None and entry_id=NULL),
        # skip extras detection entirely to avoid flooding the queue with duplicate
        # requests for extras that were already published before entry_id tracking.
        has_legacy_extras = await self._has_legacy_extras(anime_doc_id)
        if not has_legacy_extras:
            for entry in extra_entries:
                if entry.anilist_id not in existing_entry_ids:
                    new_entries.append(
                        NewEntry(
                            anilist_id=entry.anilist_id,
                            format=entry.format,
                            english_title=entry.english_title,
                            season_number=None,
                            episode_count=entry.episodes,
                            relation=entry.relation,
                        )
                    )

        # Create requests for all new entries (unless this is a detect-only pass).
        if new_entries and create:
            await self._create_requests(anime_doc_id, title, new_entries)

        return CheckResult(
            anime_doc_id=anime_doc_id,
            title=title,
            new_entries=new_entries,
            total_entries=len(entries),
        )

    async def create_requests_for(
        self, anime_doc_id: str, title: str, new_entries: list[NewEntry]
    ) -> int:
        """Commit an admin-reviewed list of new entries; return how many stuck.

        The edit-before-submit counterpart to a detect-only :meth:`check_all`:
        Gojo shows the discovered entries, the admin trims/adds, and the final
        list is handed here to create requests — same path the auto-sweep uses.
        """
        if not new_entries:
            return 0
        return await self._create_requests(anime_doc_id, title, new_entries)

    # ── helpers ─────────────────────────────────────────────────────────────

    async def _list_published_anime(self) -> list[tuple[str, str]]:
        """Return ``(anime_doc_id, title)`` for every anime with a ChannelPost."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            rows = (
                await session.execute(
                    select(ChannelPost).where(ChannelPost.main_message_id.is_not(None))
                )
            ).scalars().all()
        result: list[tuple[str, str]] = []
        for cp in rows:
            # Try to get the title from the first StoragePack.
            async with session_scope(self._c.pg_sessionmaker) as session:
                pack = (
                    await session.execute(
                        select(StoragePack)
                        .where(StoragePack.anime_doc_id == cp.anime_doc_id)
                        .limit(1)
                    )
                ).scalars().first()
            title = pack.anime_title if pack else cp.anime_doc_id
            result.append((cp.anime_doc_id, title))
        return result

    async def _resolve_anilist_id(self, anime_doc_id: str) -> int | None:
        """Find the root AniList ID from an existing request's franchise_data."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            req = (
                await session.execute(
                    select(Request)
                    .where(Request.anime_doc_id == anime_doc_id)
                    .order_by(Request.id.asc())
                    .limit(1)
                )
            ).scalars().first()
        if req is None:
            return None
        fd = req.franchise_data or {}
        # The franchise_data may have an anilist_id or we can search by title.
        anilist_id = fd.get("anilist_id")
        if anilist_id is not None:
            return int(anilist_id)
        # Fall back to searching AniList by the request's title.
        try:
            media = await self._c.anilist.search(req.anime_title)
            return media.id if media else None
        except Exception:  # noqa: BLE001
            return None

    async def _get_existing_seasons(self, anime_doc_id: str) -> set[int]:
        """Return the set of season numbers that already have storage packs."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            rows = (
                await session.execute(
                    select(StoragePack.season).where(
                        StoragePack.anime_doc_id == anime_doc_id,
                        StoragePack.season.is_not(None),
                        StoragePack.enabled.is_(True),
                    )
                )
            ).scalars().all()
            return {s for s in rows if s is not None}

    async def _get_existing_entry_ids(self, anime_doc_id: str) -> set[int]:
        """Return the set of AniList entry IDs that already have storage packs.

        Used to detect which extras (MOVIE/OVA/ONA/SPECIAL) have already been
        published. Only packs with a non-null ``entry_id`` are counted — legacy
        packs (created before the entry_id column was added) return None and are
        treated as "already handled" for safety.
        """
        async with session_scope(self._c.pg_sessionmaker) as session:
            rows = (
                await session.execute(
                    select(StoragePack.entry_id).where(
                        StoragePack.anime_doc_id == anime_doc_id,
                        StoragePack.entry_id.is_not(None),
                        StoragePack.enabled.is_(True),
                    )
                )
            ).scalars().all()
            return {eid for eid in rows if eid is not None}

    async def _has_legacy_extras(self, anime_doc_id: str) -> bool:
        """Check if this anime has legacy extra packs (season=None, entry_id=NULL).

        Legacy packs were created before the entry_id column existed. They're
        invisible to entry_id-based detection, so scanning extras would create
        duplicate requests. Return True to skip extras for this anime.
        """
        async with session_scope(self._c.pg_sessionmaker) as session:
            row = (
                await session.execute(
                    select(StoragePack.id).where(
                        StoragePack.anime_doc_id == anime_doc_id,
                        StoragePack.season.is_(None),
                        StoragePack.entry_id.is_(None),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            return row is not None

    async def _get_existing_request_seasons(self, anime_doc_id: str) -> set[int]:
        """Return the set of season numbers that already have a request.

        Used for dedup — prevents the scheduled check from creating duplicate
        requests for entries that were already discovered.
        Rejected and cancelled requests are excluded so they can be retried.
        """
        from nekofetch.domain.enums import RequestStatus

        excluded = {RequestStatus.REJECTED, RequestStatus.CANCELLED}
        async with session_scope(self._c.pg_sessionmaker) as session:
            rows = (
                await session.execute(
                    select(Request).where(
                        Request.anime_doc_id == anime_doc_id,
                        Request.season.is_not(None),
                        Request.status.not_in(excluded),  # type: ignore[arg-type]
                    )
                )
            ).scalars().all()
            return {r.season for r in rows if r.season is not None}

    async def _create_requests(
        self,
        anime_doc_id: str,
        franchise_title: str,
        new_entries: list[NewEntry],
    ) -> int:
        """Create a request for each new entry; return how many were created.

        Uses the owner's telegram_id (from config) as the requester, and
        copies the source chain from the original request for this anime.
        Skips entries that already have a request for the same anime + season.
        """
        from nekofetch.services.auth_service import AuthService
        from nekofetch.services.request_service import RequestService

        # Find the owner's telegram_id. ``AuthService.owner_ids`` resolves the
        # authoritative ``security.owner_id`` (falling back to the first env
        # admin), so a fresh install still has a requester.
        owner_ids = AuthService(self._c).owner_ids()
        if not owner_ids:
            log.warning("update_check.no_owner", anime=anime_doc_id)
            return 0
        owner_telegram_id = next(iter(owner_ids))

        # Find the original request's source chain.
        original_source = await self._get_original_source(anime_doc_id)
        if not original_source:
            log.warning(
                "update_check.no_source",
                anime=anime_doc_id,
                entries=[e.english_title for e in new_entries],
            )
            return 0

        # Dedup: skip entries that already have a request for this anime + season.
        existing_seasons = await self._get_existing_request_seasons(anime_doc_id)

        created = 0
        svc = RequestService(self._c)
        for entry in new_entries:
            if entry.season_number is not None and entry.season_number in existing_seasons:
                log.info(
                    "update_check.skipping_duplicate",
                    anime=anime_doc_id,
                    season=entry.season_number,
                )
                continue
            try:
                receipt = await svc.submit(
                    telegram_id=owner_telegram_id,
                    source=original_source,
                    source_ref=f"anilist:{entry.anilist_id}",
                    anime_title=entry.english_title or franchise_title,
                    scope=DownloadScope.FULL,
                    season=entry.season_number,
                    anime_doc_id=anime_doc_id,
                    franchise_data={
                        "anilist_id": entry.anilist_id,
                        "format": entry.format,
                        "season": entry.season_number,
                        "episodes": entry.episode_count,
                        "relation": entry.relation,
                        "english": entry.english_title,
                        "title": franchise_title,
                        "franchise_seasons": 1,
                        # Marks this as a franchise-*update* request: on publish it
                        # updates the existing distribution channel in place (append
                        # this entry's card) instead of the normal new-channel /
                        # main-channel path. See PublishingService.publish.
                        "update_entry": True,
                    },
                )
                created += 1
                log.info(
                    "update_check.request_created",
                    anime=anime_doc_id,
                    entry=entry.english_title,
                    season=entry.season_number,
                    code=receipt.code,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "update_check.request_failed",
                    anime=anime_doc_id,
                    entry=entry.english_title,
                    error=str(exc),
                )
        return created

    async def _get_original_source(self, anime_doc_id: str) -> str | None:
        """Find the source chain from the first request for this anime."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            req = (
                await session.execute(
                    select(Request)
                    .where(Request.anime_doc_id == anime_doc_id)
                    .order_by(Request.id.asc())
                    .limit(1)
                )
            ).scalars().first()
            if req is not None:
                return req.source
        return None
