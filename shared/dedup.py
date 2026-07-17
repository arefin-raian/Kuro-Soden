"""Duplicate detection — prevents accepting requests for anime that already exist.

Checks three sources in priority order:
  1. Main channel — already published and available.
  2. Distribution channel — available via distribution bot.
  3. In-progress — already being processed in the pipeline.

When a match is found, returns enough info to craft a helpful response.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from nekofetch.domain.enums import RequestStatus
from nekofetch.infrastructure.database.postgres.models import (
    ChannelPost,
    DistributionBot,
    Request,
)


@dataclass
class DedupResult:
    """Result of a duplicate check across the pipeline."""

    exists: bool = False
    source: str = ""  # "main_channel" | "distribution" | "in_progress"
    title: str = ""
    detail: str = ""  # Human-readable explanation for the user.

    # When source is "distribution":
    bot_username: str | None = None
    # When source is "main_channel":
    main_channel_link: str | None = None
    # When source is "in_progress":
    request_code: str | None = None
    current_stage: str | None = None


class DedupService:
    """Checks whether an anime already exists or is being processed."""

    # Request statuses that indicate "we're working on this".
    _IN_PROGRESS_STATUSES = {
        RequestStatus.PENDING,
        RequestStatus.APPROVED,
        RequestStatus.QUEUED,
        RequestStatus.DOWNLOADING,
        RequestStatus.PROCESSING,
        RequestStatus.READY,
    }

    def __init__(self, sessionmaker):
        self._sm = sessionmaker

    def _maybe_session(self, _session=None):
        """Context manager: yields ``_session`` if provided, else a new session."""
        if _session is not None:
            from contextlib import nullcontext
            return nullcontext(_session)
        return self._sm()

    async def check(self, anime_title: str, *, anime_doc_id: str | None = None,
                    _session=None) -> DedupResult:
        """Check all three sources for duplicates.

        Args:
            anime_title: Human-readable title (used for fuzzy matching).
            anime_doc_id: Optional AniList/Mongo document ID (exact lookup).
            _session: Optional existing session to use instead of opening a new one.
        """
        async with self._maybe_session(_session) as session:
            # 1. Check main channel (published, available).
            result = await self._check_main_channel(anime_doc_id, anime_title, session)
            if result:
                return result

            # 2. Check distribution bots (available via bot).
            result = await self._check_distribution(anime_doc_id, anime_title, session)
            if result:
                return result

            # 3. Check in-progress requests.
            result = await self._check_in_progress(anime_doc_id, anime_title, session)
            if result:
                return result

            return DedupResult(exists=False)

    async def _check_main_channel(self, anime_doc_id: str | None, title: str,
                                   session) -> DedupResult | None:
        """Check if anime is already published to the main channel."""
        if not anime_doc_id:
            return None

        post = (
            await session.execute(
                select(ChannelPost).where(
                    ChannelPost.anime_doc_id == anime_doc_id
                )
            )
        ).scalar_one_or_none()

        if post and post.main_message_id:
            # Build a public t.me link to the exact post when we can. Private
            # channels use the ``t.me/c/<internal>/<msg>`` form, where the
            # internal id is the channel id with the ``-100`` prefix stripped.
            link = None
            if post.main_channel_id:
                cid = str(post.main_channel_id)
                internal = cid[4:] if cid.startswith("-100") else cid.lstrip("-")
                link = f"https://t.me/c/{internal}/{post.main_message_id}"
            return DedupResult(
                exists=True,
                source="main_channel",
                title=title,
                detail=f"「{title}」is already available in the main channel!",
                main_channel_link=link,
            )
        return None

    async def _check_distribution(self, anime_doc_id: str | None, title: str,
                                    session) -> DedupResult | None:
        """Check if anime has a distribution bot/channel."""
        if not anime_doc_id:
            return None

        bot = (
            await session.execute(
                select(DistributionBot).where(
                    DistributionBot.anime_doc_id == anime_doc_id,
                    DistributionBot.enabled.is_(True),
                )
            )
        ).scalar_one_or_none()

        if bot:
            return DedupResult(
                exists=True,
                source="distribution",
                title=title,
                detail=f"「{title}」is available via @{bot.username or 'our distribution bot'}!",
                bot_username=bot.username,
            )
        return None

    async def _check_in_progress(self, anime_doc_id: str | None, title: str,
                                   session) -> DedupResult | None:
        """Check if anime is already being processed."""
        # Try exact doc_id match first.
        if anime_doc_id:
            req = (
                await session.execute(
                    select(Request).where(
                        Request.anime_doc_id == anime_doc_id,
                        Request.status.in_(self._IN_PROGRESS_STATUSES),
                    ).order_by(Request.created_at.desc()).limit(1)
                )
            ).scalar_one_or_none()

            if req:
                return self._build_in_progress_result(req)

        # Fall back to title match.
        req = (
            await session.execute(
                select(Request).where(
                    Request.anime_title.ilike(f"%{title}%"),
                    Request.status.in_(self._IN_PROGRESS_STATUSES),
                ).order_by(Request.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()

        if req:
            return self._build_in_progress_result(req)

        return None

    @staticmethod
    def _build_in_progress_result(req: Request) -> DedupResult:
        """Build a friendly result for in-progress requests."""
        stage_labels = {
            "pending": "awaiting source assignment",
            "approved": "approved, queuing for download",
            "queued": "in the download queue",
            "downloading": "currently downloading",
            "processing": "being processed",
            "ready": "awaiting publishing",
        }
        stage = req.status if isinstance(req.status, str) else str(req.status.value)
        stage_display = stage_labels.get(stage, stage)

        return DedupResult(
            exists=True,
            source="in_progress",
            title=req.anime_title,
            detail=(
                f"「{req.anime_title}」has already been requested by someone else!\n\n"
                f"📋 Request: {req.code}\n"
                f"📊 Status: {stage_display}\n\n"
                f"✨ You'll receive the link once it's published!"
            ),
            request_code=req.code,
            current_stage=stage_display,
        )
