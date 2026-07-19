"""Broadcast one message to every distribution channel.

An operator can push a single announcement to *all* distribution channels at
once — a maintenance notice, a request drive, a giveaway ping. Two shapes:

* **permanent** — the message stays until manually removed, and
* **timed** — the message is auto-deleted after ``delete_after_minutes``.

Durability matters: the APScheduler that runs jobs is in-memory, so a bot
restart would forget a pending deletion. We therefore persist every delivered
copy as a :class:`ChannelBroadcast` row carrying its ``delete_at``; the
scheduler's :meth:`sweep_expired` job (registered in ``bots/manager.py``, same
cadence as the access-link sweep) deletes any past-due row and marks it done.
That mirrors the :class:`DistributionService` link-expiry pattern, so a timed
broadcast is honoured even across a crash/restart.

The **main channel is never a target** — this is distribution channels only,
matching how :class:`MaintenanceService` enumerates ban-check targets.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.infrastructure.database.postgres.models import (
    ChannelBroadcast,
    DistributionBot,
)
from nekofetch.infrastructure.database.postgres.session import session_scope

log = get_logger(__name__)

# Pace sends so a large channel list doesn't trip Telegram's flood limits — the
# same 50 ms spacing the per-user broadcast uses.
_SEND_SPACING_SECONDS = 0.05


@dataclass(slots=True)
class BroadcastResult:
    """Outcome of one broadcast run."""
    batch_id: str
    targets: int = 0
    sent: int = 0
    failed: int = 0
    delete_at: datetime | None = None
    errors: list[str] = field(default_factory=list)


class BroadcastService:
    def __init__(self, container: Container) -> None:
        self._c = container

    # ── public API ───────────────────────────────────────────────────────────

    async def broadcast_text(
        self, text: str, *, delete_after_minutes: int | None = None,
        silent: bool = False, client=None,
    ) -> BroadcastResult:
        """Send a plain text/HTML message to every distribution channel."""
        from pyrogram.enums import ParseMode

        client = client or getattr(self._c, "admin_client", None)

        async def _send(cl, chat_id: int) -> int | None:
            msg = await cl.send_message(
                chat_id, text, parse_mode=ParseMode.HTML,
                disable_notification=silent,
            )
            return getattr(msg, "id", None)

        return await self._deliver(
            client, _send, delete_after_minutes=delete_after_minutes,
        )

    async def broadcast_copy(
        self, from_chat_id: int, message_id: int, *,
        delete_after_minutes: int | None = None, silent: bool = False,
        client=None,
    ) -> BroadcastResult:
        """Copy an existing message (any media) to every distribution channel.

        ``copy`` (not forward) so the post shows no "forwarded from" header —
        the announcement reads as native channel content.
        """
        client = client or getattr(self._c, "admin_client", None)

        async def _send(cl, chat_id: int) -> int | None:
            copied = await cl.copy_message(
                chat_id=chat_id, from_chat_id=from_chat_id,
                message_id=message_id, disable_notification=silent,
            )
            return getattr(copied, "id", None)

        return await self._deliver(
            client, _send, delete_after_minutes=delete_after_minutes,
        )

    # ── delivery core ────────────────────────────────────────────────────────

    async def _deliver(
        self, client, send, *, delete_after_minutes: int | None,
    ) -> BroadcastResult:
        """Fan a per-channel ``send(client, chat_id) -> message_id`` out to all
        distribution channels, recording each delivered copy for later sweep.

        ``delete_after_minutes`` of ``None`` (or ``<= 0``) means permanent.
        """
        batch_id = secrets.token_hex(8)
        result = BroadcastResult(batch_id=batch_id)

        if client is None:
            log.warning("broadcast.no_client", batch=batch_id)
            return result

        delete_at: datetime | None = None
        if delete_after_minutes and delete_after_minutes > 0:
            delete_at = datetime.now(timezone.utc) + timedelta(
                minutes=delete_after_minutes
            )
        result.delete_at = delete_at

        chat_ids = await self._channel_chat_ids()
        result.targets = len(chat_ids)
        if not chat_ids:
            log.info("broadcast.no_channels", batch=batch_id)
            return result

        rows: list[ChannelBroadcast] = []
        for chat_id in chat_ids:
            try:
                message_id = await send(client, chat_id)
            except Exception as exc:  # noqa: BLE001 — one channel down ≠ abort
                result.failed += 1
                result.errors.append(f"{chat_id}: {exc}")
                log.warning("broadcast.send_failed", batch=batch_id,
                            chat_id=chat_id, error=str(exc))
                await asyncio.sleep(_SEND_SPACING_SECONDS)
                continue
            if message_id is None:
                result.failed += 1
                log.warning("broadcast.no_message_id", batch=batch_id, chat_id=chat_id)
                await asyncio.sleep(_SEND_SPACING_SECONDS)
                continue
            result.sent += 1
            rows.append(ChannelBroadcast(
                batch_id=batch_id, chat_id=chat_id, message_id=message_id,
                delete_at=delete_at, deleted=False,
            ))
            await asyncio.sleep(_SEND_SPACING_SECONDS)

        # Persist every delivered copy so the sweep can honour delete_at even
        # after a restart (permanent rows are kept for auditing/manual purge).
        if rows:
            async with session_scope(self._c.pg_sessionmaker) as session:
                session.add_all(rows)

        log.info("broadcast.done", batch=batch_id, targets=result.targets,
                 sent=result.sent, failed=result.failed,
                 delete_at=delete_at.isoformat() if delete_at else None)
        return result

    async def _channel_chat_ids(self) -> list[int]:
        """Every enabled distribution *channel*'s chat id (main channel excluded)."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            channels = (
                await session.execute(
                    select(DistributionBot).where(
                        DistributionBot.is_channel.is_(True),
                        DistributionBot.enabled.is_(True),
                    )
                )
            ).scalars().all()
        return [int(ch.chat_id) for ch in channels if ch.chat_id]

    # ── scheduled auto-deletion ────────────────────────────────────────────────

    async def sweep_expired(self, *, client=None) -> int:
        """Scheduler job: delete every past-due broadcast copy. Returns count.

        Durable backstop for timed broadcasts: any :class:`ChannelBroadcast`
        with a ``delete_at`` in the past and ``deleted`` still false is removed
        from Telegram and flagged. A copy that's already gone (stale id) is
        flagged too, so a transient miss never wedges the sweep in a loop.
        """
        client = client or getattr(self._c, "admin_client", None)
        if client is None:
            return 0

        now = datetime.now(timezone.utc)
        async with session_scope(self._c.pg_sessionmaker) as session:
            rows = (
                await session.execute(
                    select(ChannelBroadcast).where(
                        ChannelBroadcast.deleted.is_(False),
                        ChannelBroadcast.delete_at.is_not(None),
                        ChannelBroadcast.delete_at < now,
                    )
                )
            ).scalars().all()
            deleted = 0
            for row in rows:
                try:
                    await client.delete_messages(row.chat_id, row.message_id)
                except Exception as exc:  # noqa: BLE001 — stale/gone still resolves
                    log.warning("broadcast.sweep.delete_failed",
                                chat_id=row.chat_id, message_id=row.message_id,
                                error=str(exc))
                row.deleted = True
                deleted += 1
            if deleted:
                log.info("broadcast.sweep.done", deleted=deleted)
            return deleted
