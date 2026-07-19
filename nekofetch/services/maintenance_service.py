"""Monthly maintenance — update sweep + ban check.

Two operator-facing jobs Gojo runs monthly (and on demand):

* **update check** (:meth:`scan_updates`) — a *detect-only* franchise sweep
  (``UpdateCheckService.check_all(create=False)``) that finds finished seasons,
  movies, and extras not yet published, without touching the queue. The admin
  reviews/trims the list, then commits via
  :meth:`UpdateCheckService.create_requests_for` — the edit-before-submit flow.

* **ban check** (:meth:`probe_channels`) — probe every distribution channel (and
  the main channel) with a cheap ``get_chat`` through the admin client. A channel
  that raises ``CHANNEL_INVALID`` / ``CHAT_ADMIN_REQUIRED`` / ``USER_BANNED`` (or
  simply can't be resolved) is reported as down so recovery can kick in.

Both are pure orchestration over existing services — no new persistence — so they
stay safe to run on a scheduler as well as from a button.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.infrastructure.database.postgres.models import DistributionBot
from nekofetch.infrastructure.database.postgres.session import session_scope

log = get_logger(__name__)

# Substrings in a Pyrogram error that mean "this channel is gone / we're out".
_BAN_MARKERS = (
    "CHANNEL_INVALID", "CHANNEL_PRIVATE", "CHAT_ADMIN_REQUIRED",
    "USER_BANNED", "PEER_ID_INVALID", "CHAT_WRITE_FORBIDDEN",
)


@dataclass(slots=True)
class ChannelProbe:
    """One channel's reachability result."""
    anime_doc_id: str | None
    chat_id: int
    name: str
    reachable: bool
    error: str | None = None


@dataclass(slots=True)
class BanCheckResult:
    checked: int = 0
    banned: list[ChannelProbe] = field(default_factory=list)


class MaintenanceService:
    def __init__(self, container: Container) -> None:
        self._c = container

    # ── Update sweep (detect-only) ─────────────────────────────────────────────

    async def scan_updates(self):
        """Detect-only franchise sweep; returns actionable ``CheckResult``s only."""
        from nekofetch.services.update_check_service import UpdateCheckService

        results = await UpdateCheckService(self._c).check_all(create=False)
        return [r for r in results if r.new_entries]

    # ── Ban check ──────────────────────────────────────────────────────────────

    async def probe_channels(self) -> BanCheckResult:
        """Probe every distribution channel + the main channel for a ban.

        Uses the admin client's ``get_chat`` as a cheap liveness probe. Bots
        (``is_channel`` False) are skipped — they have their own ban-health path
        in the orchestrator; here we care about the channels whose posts we back
        up and restore.
        """
        result = BanCheckResult()
        client = getattr(self._c, "admin_client", None)
        if client is None:
            return result

        targets: list[ChannelProbe] = []

        # Distribution channels.
        async with session_scope(self._c.pg_sessionmaker) as session:
            channels = (
                await session.execute(
                    select(DistributionBot).where(DistributionBot.is_channel.is_(True))
                )
            ).scalars().all()
        for ch in channels:
            if ch.chat_id:
                targets.append(ChannelProbe(
                    anime_doc_id=ch.anime_doc_id, chat_id=ch.chat_id,
                    name=ch.name, reachable=True,
                ))

        # The main channel itself.
        main_id = getattr(self._c.config.main_channel, "channel_id", 0)
        if main_id:
            targets.append(ChannelProbe(
                anime_doc_id=None, chat_id=main_id,
                name="Main Channel", reachable=True,
            ))

        for probe in targets:
            result.checked += 1
            try:
                await client.get_chat(probe.chat_id)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                # Only count as banned on a recognized "gone" error; a transient
                # network blip shouldn't trigger a false recovery.
                if any(m in msg.upper() for m in _BAN_MARKERS):
                    probe.reachable = False
                    probe.error = msg
                    result.banned.append(probe)
                    log.warning("maintenance.channel_down",
                                chat_id=probe.chat_id, error=msg)
                else:
                    log.debug("maintenance.probe_error",
                              chat_id=probe.chat_id, error=msg)

        log.info("maintenance.ban_check.done",
                 checked=result.checked, banned=len(result.banned))
        return result
