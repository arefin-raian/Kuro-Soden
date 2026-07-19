"""Main-channel backup & restore — survive a channel ban byte-for-byte.

The main channel is the store's public face. If it's banned, every post has to
reappear on a fresh channel exactly as it was — same caption styling, same photo,
same Index/Download buttons, same divider stickers — with **no re-rendering and no
re-fetching** (TMDB/AniList may have changed, thumbnails may be gone). That's only
possible if we captured everything ahead of time.

:class:`BackupService` does two jobs:

* **capture** (:meth:`backup_all` / :meth:`backup_one`) — snapshot each live
  ``ChannelPost`` into a :class:`PublishedPostBackup`: the finished caption HTML,
  the photo (mirrored to catbox + telegraph via :mod:`image_backup` so it outlives
  the original CDN), the structured button layout, and the divider sticker id.
* **restore** (:meth:`restore_to_channel`) — rebuild every backed-up post on a new
  channel from those rows alone, with pacing (all at once / N per day / every X
  minutes), then repoint ``ChannelPost`` + config at the new channel.

Capture is best-effort per post: one unreachable image or message never aborts the
sweep. Restore reports how many posts it rebuilt so the operator sees progress.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.infrastructure.database.postgres.models import (
    ChannelPost,
    PublishedPostBackup,
)
from nekofetch.infrastructure.database.postgres.session import session_scope

log = get_logger(__name__)


@dataclass(slots=True)
class BackupStats:
    posts: int = 0          # ChannelPost rows considered
    backed_up: int = 0      # snapshots written/updated
    images_mirrored: int = 0  # images that landed on at least one durable host


@dataclass(slots=True)
class RestoreStats:
    total: int = 0          # backups to restore
    restored: int = 0       # messages successfully re-posted
    failed: int = 0


def _markup_to_rows(markup: InlineKeyboardMarkup | None) -> list | None:
    """Serialize an inline keyboard to plain JSON rows for storage.

    Main-channel buttons are all URL buttons (Index/Download), so we keep
    ``text`` + ``url`` (and ``callback_data`` if a future button uses it).
    """
    if markup is None:
        return None
    rows: list[list[dict]] = []
    for row in markup.inline_keyboard:
        out: list[dict] = []
        for btn in row:
            entry: dict = {"text": btn.text}
            if btn.url:
                entry["url"] = btn.url
            if btn.callback_data:
                entry["callback_data"] = btn.callback_data
            out.append(entry)
        if out:
            rows.append(out)
    return rows or None


def _rows_to_markup(rows: list | None) -> InlineKeyboardMarkup | None:
    """Rebuild an inline keyboard from stored JSON rows (inverse of above)."""
    if not rows:
        return None
    kb: list[list[InlineKeyboardButton]] = []
    for row in rows:
        out: list[InlineKeyboardButton] = []
        for entry in row:
            out.append(InlineKeyboardButton(
                entry.get("text", " "),
                url=entry.get("url"),
                callback_data=entry.get("callback_data"),
            ))
        if out:
            kb.append(out)
    return InlineKeyboardMarkup(kb) if kb else None


class BackupService:
    def __init__(self, container: Container) -> None:
        self._c = container
        self.cfg = container.config.main_channel

    # ── Capture ──────────────────────────────────────────────────────────────

    async def backup_all(self) -> BackupStats:
        """Snapshot every tracked main-channel post. Best-effort per post."""
        stats = BackupStats()
        async with session_scope(self._c.pg_sessionmaker) as session:
            posts = (
                await session.execute(
                    select(ChannelPost).where(ChannelPost.main_message_id.isnot(None))
                )
            ).scalars().all()
        stats.posts = len(posts)
        for post in posts:
            ok = await self.backup_one(post.anime_doc_id)
            if ok:
                stats.backed_up += 1
                if ok.image_catbox_url or ok.image_telegraph_url:
                    stats.images_mirrored += 1
        log.info("backup.all.done", posts=stats.posts, backed_up=stats.backed_up)
        return stats

    async def backup_one(self, anime_doc_id: str) -> PublishedPostBackup | None:
        """Snapshot a single post into a ``PublishedPostBackup`` (upsert).

        Rebuilds the exact caption + buttons from the same service the publisher
        uses, mirrors the photo to durable hosts, and records the divider sticker.
        Returns the saved row, or ``None`` if there's nothing live to back up.
        """
        from nekofetch.services.main_channel_service import MainChannelService

        async with session_scope(self._c.pg_sessionmaker) as session:
            post = (
                await session.execute(
                    select(ChannelPost).where(ChannelPost.anime_doc_id == anime_doc_id)
                )
            ).scalar_one_or_none()
            if post is None or not post.main_message_id:
                return None

        svc = MainChannelService(self._c)
        facts = await svc.gather_facts(anime_doc_id)
        caption = svc._caption(facts)
        markup = await svc._buttons(facts)
        source_url = facts.backdrop_url or facts.poster_url or ""

        # Mirror the photo onto independent hosts so it survives the ban.
        catbox_url = telegraph_url = None
        if source_url:
            from kurosoden.shared.image_backup import backup_image

            mirrored = await backup_image(self._c, source_url)
            catbox_url, telegraph_url = mirrored.catbox_url, mirrored.telegraph_url

        divider = getattr(self.cfg, "divider_sticker_id", None)

        async with session_scope(self._c.pg_sessionmaker) as session:
            row = (
                await session.execute(
                    select(PublishedPostBackup).where(
                        PublishedPostBackup.anime_doc_id == anime_doc_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = PublishedPostBackup(anime_doc_id=anime_doc_id)
                session.add(row)
            row.title = facts.title
            row.caption = caption
            row.image_source_url = source_url or None
            row.image_catbox_url = catbox_url
            row.image_telegraph_url = telegraph_url
            row.button_data = _markup_to_rows(markup)
            row.divider_sticker_id = divider
            row.source_channel_id = post.main_channel_id
            row.source_message_id = post.main_message_id
            await session.commit()
            await session.refresh(row)
            log.info("backup.one.done", anime=anime_doc_id,
                     mirrored=bool(catbox_url or telegraph_url))
            return row

    # ── Restore ──────────────────────────────────────────────────────────────

    async def restore_to_channel(
        self, new_channel_id: int, *,
        per_batch: int = 0, delay_seconds: float = 0.0,
        update_config: bool = True,
    ) -> RestoreStats:
        """Rebuild every backed-up post on ``new_channel_id`` from the DB alone.

        Pacing: ``per_batch`` posts, then sleep ``delay_seconds`` before the next
        batch (``per_batch=0`` → no pacing, post as fast as the API allows). When
        ``update_config`` is set, the main-channel id is repointed and each
        ``ChannelPost`` is updated to the new message id so future edits land on
        the restored post.

        No re-rendering: images come from the mirrored URLs, captions and buttons
        from the stored snapshot. A per-post failure is counted and skipped.
        """
        client = getattr(self._c, "admin_client", None)
        if client is None:
            return RestoreStats()

        async with session_scope(self._c.pg_sessionmaker) as session:
            backups = (
                await session.execute(
                    select(PublishedPostBackup).order_by(PublishedPostBackup.id)
                )
            ).scalars().all()

        stats = RestoreStats(total=len(backups))
        divider = getattr(self.cfg, "divider_sticker_id", None)
        posted_in_batch = 0

        for b in backups:
            # Divider sticker first (channel layout detail), best-effort.
            sticker = b.divider_sticker_id or divider
            if sticker:
                try:
                    await client.send_sticker(new_channel_id, sticker)
                except Exception as exc:  # noqa: BLE001
                    log.debug("restore.divider.failed", error=str(exc))

            photo = b.image_catbox_url or b.image_telegraph_url or b.image_source_url
            markup = _rows_to_markup(b.button_data)
            try:
                if photo:
                    sent = await client.send_photo(
                        new_channel_id, photo, caption=b.caption or "",
                        reply_markup=markup, parse_mode=ParseMode.HTML,
                    )
                else:
                    sent = await client.send_message(
                        new_channel_id, b.caption or "",
                        reply_markup=markup, parse_mode=ParseMode.HTML,
                    )
                stats.restored += 1
            except Exception as exc:  # noqa: BLE001
                stats.failed += 1
                log.warning("restore.post.failed", anime=b.anime_doc_id, error=str(exc))
                continue

            if update_config:
                await self._repoint(b.anime_doc_id, new_channel_id, sent.id)

            posted_in_batch += 1
            if per_batch and posted_in_batch >= per_batch:
                posted_in_batch = 0
                if delay_seconds:
                    await asyncio.sleep(delay_seconds)

        if update_config and stats.restored:
            try:
                from nekofetch.services.settings_service import SettingsService

                await SettingsService(self._c).set_value(
                    "main_channel", "channel_id", new_channel_id
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("restore.config_write_failed", error=str(exc))

        log.info("restore.done", total=stats.total, restored=stats.restored,
                 failed=stats.failed, channel=new_channel_id)
        return stats

    async def _repoint(self, anime_doc_id: str, channel_id: int, message_id: int) -> None:
        """Point the ChannelPost row at the restored message on the new channel."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            post = (
                await session.execute(
                    select(ChannelPost).where(ChannelPost.anime_doc_id == anime_doc_id)
                )
            ).scalar_one_or_none()
            if post is None:
                post = ChannelPost(anime_doc_id=anime_doc_id)
                session.add(post)
            post.main_channel_id = channel_id
            post.main_message_id = message_id
            await session.commit()
