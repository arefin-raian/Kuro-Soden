"""Publishing service — the approval gate before content becomes user-visible.

Lists requests in READY state, and publishes / reprocesses / cancels them. Publishing
marks the request's files visible and (in a full build) deploys them to the bound
distribution bot.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from nekofetch.core.container import Container
from nekofetch.core.exceptions import NotFound
from nekofetch.domain.enums import RequestStatus
from nekofetch.infrastructure.database.postgres.models import DownloadJob, MediaFile, Request
from nekofetch.infrastructure.database.postgres.session import session_scope
from nekofetch.infrastructure.repositories.request_repo import RequestRepository
from nekofetch.core.parsing import clean_anilist_id


@dataclass(slots=True)
class ApprovalSummary:
    code: str
    title: str
    files: int
    resolution: str | None
    audio: str | None
    has_thumbnail: bool


class PublishingService:
    def __init__(self, container: Container) -> None:
        self._c = container

    async def list_ready(self, *, limit: int = 10) -> list[ApprovalSummary]:
        async with session_scope(self._c.pg_sessionmaker) as session:
            reqs = (
                await session.execute(
                    select(Request).where(Request.status == RequestStatus.READY).limit(limit)
                )
            ).scalars().all()
            out: list[ApprovalSummary] = []
            for req in reqs:
                files = await self._files_for_request(session, req.id)
                first = files[0] if files else None
                out.append(
                    ApprovalSummary(
                        code=req.code,
                        title=req.anime_title,
                        files=len(files),
                        resolution=first.resolution if first else None,
                        audio=(first.audio.value if first and first.audio else None),
                        has_thumbnail=any(
                            f.local_path and f.local_path.endswith(".thumb.jpg") for f in files
                        ),
                    )
                )
            return out

    async def _files_for_request(self, session, request_id: int) -> list[MediaFile]:
        job_ids = (
            await session.execute(
                select(DownloadJob.id).where(DownloadJob.request_id == request_id)
            )
        ).scalars().all()
        if not job_ids:
            return []
        return list(
            (await session.execute(select(MediaFile).where(MediaFile.job_id.in_(job_ids))))
            .scalars()
            .all()
        )

    async def upload_to_storage(self, code: str, *, on_progress=None) -> int:
        """Upload a request's processed files to the storage (DB) channel as packs.

        This is **automatic** — it runs straight after processing, independent of
        the main-channel publish/approval gate. Putting verified files into the
        database channel is just part of the pipeline; "publishing" (posting to the
        main channel, index, etc.) is a separate, deliberate action.
        """
        from pathlib import Path

        verify_on = self._c.config.processing.verify_files
        async with session_scope(self._c.pg_sessionmaker) as session:
            req = await RequestRepository(session).get_by_code(code)
            if req is None:
                raise NotFound(code)
            files = await self._files_for_request(session, req.id)
            # Upload every file that exists on disk. The verify GATE only applies when
            # verification is actually enabled — otherwise files are never flagged
            # verified and NOTHING would ever reach the DB channel (the bug where DB
            # uploads "didn't consistently happen").
            files = [
                f for f in files
                if f.local_path and Path(f.local_path).exists()
                and (f.verified or not verify_on)
            ]
            anime_doc_id = req.anime_doc_id or clean_anilist_id(req.source_ref)
            title = req.anime_title
            # Extract the AniList entry ID from franchise_data so storage packs
            # track which specific entry (season/movie/OVA) the files belong to.
            fd = req.franchise_data or {}
            req_entry_id: int | None = fd.get("anilist_id") or fd.get("season_anilist_id")
            snapshot = [
                {"season": f.season, "season_part": f.season_part,
                 "episode": f.episode, "resolution": f.resolution,
                 "audio": f.audio, "path": f.local_path,
                 "original_name": f.original_name,
                 "entry_id": req_entry_id}
                for f in files
            ]

        await self._upload_packs(anime_doc_id, title, snapshot, on_progress=on_progress)

        # Uploaded to the storage channel — delivery serves from Telegram file_ids,
        # not local disk, so every local file is now redundant. Delete them all so
        # nothing accumulates. Best-effort: cleanup must never fail the pipeline.
        self._cleanup_local_files(snapshot, code=code, title=title)

        from nekofetch.services.log_channel_service import LogChannelService

        await LogChannelService(self._c).event(
            "download", "stored", code=code, anime=title, files=len(snapshot),
        )
        return len(snapshot)

    def _cleanup_local_files(self, snapshot: list[dict], *, code: str, title: str) -> None:
        """Delete every local file for a request after a successful storage upload.

        Covers all three places files can live so nothing is left behind:
          * ``work/<folder>``           — the processed outputs that were uploaded
          * ``work/_manual/<code>``     — a manual upload's raw intake
          * ``library/<slug>``          — a manual upload's renamed copies (staging)
        The manual paths simply don't exist for non-manual sources, so removing them
        is a harmless no-op there.
        """
        import shutil
        from pathlib import Path

        from nekofetch.core.logging import get_logger
        from nekofetch.sources.local import _slug

        log = get_logger(__name__)
        targets: set[Path] = set()

        for item in snapshot:
            p = item.get("path")
            if not p:
                continue
            fp = Path(p)
            # Only a "work/<folder>" directory is a safe rmtree target; otherwise
            # just remove the individual file.
            if fp.parent.parent.name == "work":
                targets.add(fp.parent)
            else:
                fp.unlink(missing_ok=True)

        storage = Path(self._c.env.storage_path)
        if code:
            targets.add(storage / "work" / "_manual" / code)
        if title:
            targets.add(storage / "library" / _slug(title))

        for d in targets:
            shutil.rmtree(d, ignore_errors=True)
        log.info("storage.cleanup.done", code=code, removed=len(targets))

    async def publish(self, code: str) -> int:
        """Make stored content user-visible: wait for thumbnails → create bot
        → post to main channel + index.

        New flow per operator feedback:
          1. Mark the request PUBLISHED (file.published=True, DB row updated).
          2. Call ThumbnailOrchestratorService so the bot/cards use
             admin-generated thumbnails (logo/poster/bg → Playwright render).
             Polls the workflow state and either waits it out OR marks the
             pipeline ready once the admin clicks "Skip Custom Thumbnails".
             Has a hard timeout so an absent admin can't block bot creation.
          3. Create distribution bot (or channel if bot limit is exhausted).
          4. Post to the main channel (the Download button now has the bot
             username); main channel uses the FIRST season's generated
             thumbnail as its post photo.
          5. Index + stats + notification fan-out.
        """
        async with session_scope(self._c.pg_sessionmaker) as session:
            req = await RequestRepository(session).get_by_code(code)
            if req is None:
                raise NotFound(code)
            user_id = req.user_id
            files = await self._files_for_request(session, req.id)
            for f in files:
                f.published = True
            req.status = RequestStatus.PUBLISHED
            count = len(files)
            anime_doc_id = req.anime_doc_id or clean_anilist_id(req.source_ref)
            title = req.anime_title
            first = next((f for f in files if f.local_path), None)
            res = first.resolution if first else None
            aud = first.audio.value if first and first.audio else None

        from nekofetch.services.analytics_service import AnalyticsService

        await AnalyticsService(self._c).record(
            "publish", anime_doc_id=anime_doc_id, data={"code": code, "files": count}
        )

        # Step 1: Wait for the thumbnail generation step to complete (or time
        # out / be skipped). The orchestrator surfaces the generated thumbnail
        # URL map to BotContentService + MainChannelService downstream.
        # No-op when the thumbnail_channel feature is disabled in config —
        # the orchestrator short-circuits and the rest of the pipeline uses
        # AniList posters throughout.
        #
        # All THREE gates must be on — if telegraph_access_token is empty,
        # :class:`ThumbnailChannelService.add_to_queue` short-circuits without
        # writing workflow entries, leaving ``is_complete()`` permanently
        # False. Without this guard we would burn the full 10-minute timeout
        # before falling back to AniList posters on every misconfigured host.
        if (
            self._c.config.features.thumbnail_generation
            and self._c.config.thumbnail_channel.enabled
            and self._c.config.thumbnail_channel.telegraph_access_token
        ):
            try:
                await self._wait_for_thumbnails(anime_doc_id, title)
            except Exception as exc:  # noqa: BLE001 - never block publish on thumb step
                from nekofetch.core.logging import get_logger
                get_logger(__name__).warning(
                    "publish.thumbnails.wait.failed",
                    anime=anime_doc_id, error=str(exc),
                )

        # Step 2: Create distribution bot (if auto-create is enabled and feature is on).
        if self._c.config.features.distribution_bots and self._c.config.bot.auto_create_on_publish:
            from nekofetch.services.bot_orchestrator import BotOrchestratorService

            await BotOrchestratorService(self._c).ensure_bot_for_anime(anime_doc_id)

        # Step 3: Post to main channel (uses first season's generated thumbnail).
        from nekofetch.services.index_channel_service import IndexChannelService
        from nekofetch.services.main_channel_service import MainChannelService

        await MainChannelService(self._c).publish(anime_doc_id)
        await IndexChannelService(self._c).refresh_letter(
            IndexChannelService.letter_of(title)
        )

        from nekofetch.services.log_channel_service import LogChannelService

        await LogChannelService(self._c).event(
            "publish", "approved", code=code, anime=title, files=count,
            audio=aud, resolution=res,
        )

        # Refresh database stats (pinned message in index channel). Best-effort:
        # a stats hiccup must never fail an otherwise-successful publish.
        try:
            from nekofetch.services.stats_service import StatsService

            await StatsService(self._c).refresh()
        except Exception as exc:  # noqa: BLE001
            from nekofetch.core.logging import get_logger

            get_logger(__name__).warning("publish.stats_refresh.failed", error=str(exc))

        if user_id:
            from nekofetch.services.notification_service import NotificationService
            await NotificationService(self._c).request_published(user_id, title, code)
        return count

    async def _wait_for_thumbnails(self, anime_doc_id: str, title: str) -> None:
        """Bridge from the storage upload step to bot creation — queues and waits.

        Builds the per-entry thumbnail request list from the franchise walk
        (AniList) and TMDB metadata, then drives the orchestrator's polling
        loop. Skips generation entirely when the franchise walk returned zero
        entries (Telegram-source titles that don't have AniList relations).

        Emits a ``download.thumbnail_requested`` event so the Control Center
        shows admins that new thumb work is pending.
        """
        from nekofetch.core.logging import get_logger
        from nekofetch.services.bot_content import BotContentService
        from nekofetch.services.thumbnail_orchestrator_service import (
            ThumbnailOrchestratorService,
        )

        log = get_logger(__name__)

        # Re-use bot_content's franchise walk to build the entries list with
        # the same anilist_id we want thumbnails for. Avoids re-implementing
        # the AniList BFS in two places.
        bcs = BotContentService(self._c)
        try:
            meta = await bcs._gather_metadata(anime_doc_id)
            franchise = await bcs._walk_franchise(anime_doc_id, meta)
        except Exception as exc:  # noqa: BLE001 - walk failures shouldn't block publish
            log.debug("publish.franchise_walk.failed",
                      anime=anime_doc_id, error=str(exc))
            return

        tv_entries = franchise.get("tv", []) or []
        extra_entries = franchise.get("extras", []) or []
        if not tv_entries and not extra_entries:
            log.info("publish.thumbnails.skipped.no_entries",
                     anime=anime_doc_id, title=title)
            return

        # Use the shared helper so the labels and AniList IDs line up with
        # :meth:`BotContentService._queue_for_thumbnails`. One source of truth
        # for the per-entry shape.
        entries = BotContentService.build_thumbnail_entries(franchise)

        orch = ThumbnailOrchestratorService(self._c)
        await orch.request_thumbnails(anime_doc_id, str(title), entries)
        completed = await orch.wait_for_thumbnails(anime_doc_id)
        log.info(
            "publish.thumbnails.wait.result",
            anime=anime_doc_id,
            generated=completed,
            skipped=(not completed),
        )

    async def _upload_packs(self, anime_doc_id: str, title: str, files: list[dict],
                            *, on_progress=None) -> None:
        """Group published files by (season, resolution, audio, entry_id) and upload each as a pack."""
        if not self._c.config.storage_channel.enabled or not files:
            return
        from pathlib import Path

        from nekofetch.core.exceptions import FeatureDisabled
        from nekofetch.services.storage_channel_service import StorageChannelService

        storage = StorageChannelService(self._c)
        groups: dict[tuple, list[dict]] = {}
        for f in files:
            groups.setdefault((f.get("season"), f.get("season_part"), f["resolution"], f["audio"], f.get("entry_id")), []).append(f)

        from nekofetch.services.processing.stages import (
            POSTER_THUMB_NAME,
            _content_type_label,
        )

        for (season, season_part, resolution, audio, entry_id), items in groups.items():
            if not resolution or audio is None:
                continue
            items.sort(key=lambda x: (x["episode"] or 0))
            episodes = [i["episode"] for i in items if i["episode"] is not None]
            # Content type via the shared classifier (Season / Movie / OVA / ONA /
            # Special), refined by a filename hint so an extra reads naturally in
            # the header instead of a blanket "Special". Keeps header + filename in
            # lock-step (both go through processing.stages).
            name_hint = items[0].get("original_name") or items[0].get("path") or ""
            ct = _content_type_label(season, len(items), name_hint)
            # Find the poster the thumbnail stage wrote — it's a sibling of the media
            # files. Search each item's folder so EVERY pack gets the thumbnail even
            # if the first item happens to live elsewhere.
            poster = next(
                (p for i in items
                 if (p := Path(i["path"]).with_name(POSTER_THUMB_NAME)).exists()),
                None,
            )
            try:
                await storage.upload_pack(
                    storage.key_from(anime_doc_id, season, resolution, audio,
                                     season_part=season_part, entry_id=entry_id),
                    title=title,
                    file_paths=[Path(i["path"]) for i in items],
                    episode_from=min(episodes) if episodes else None,
                    episode_to=max(episodes) if episodes else None,
                    content_type=ct,
                    thumb=poster,
                    on_progress=on_progress,
                )
            except FeatureDisabled:
                return
            except Exception as exc:  # noqa: BLE001 - one pack failing shouldn't abort publish
                from nekofetch.core.logging import get_logger

                get_logger(__name__).warning("publish.upload_pack.failed",
                                             season=season, resolution=resolution, error=str(exc))

    async def reprocess(self, code: str) -> None:
        async with session_scope(self._c.pg_sessionmaker) as session:
            req = await RequestRepository(session).get_by_code(code)
            if req is None:
                raise NotFound(code)
            job = (
                await session.execute(
                    select(DownloadJob).where(DownloadJob.request_id == req.id)
                )
            ).scalars().first()
            job_id = job.id if job else None
        if job_id is not None:
            from nekofetch.services.processing.pipeline import ProcessingPipeline

            await ProcessingPipeline(self._c).run_for_job(job_id)

    async def cancel(self, code: str) -> None:
        async with session_scope(self._c.pg_sessionmaker) as session:
            req = await RequestRepository(session).get_by_code(code)
            if req is None:
                raise NotFound(code)
            req.status = RequestStatus.REJECTED
