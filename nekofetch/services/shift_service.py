"""Shift Service — admin duty rotation for the Control Center & Asset Forge.

Manages which admin is currently on duty for each operational channel (log channel
"Control Center" and thumbnail channel "Asset Forge"). Provides assign, release,
takeover request, relief request, and handoff flows.

State is persisted in Redis so it survives restarts.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import ShiftStatus

log = get_logger(__name__)

# ── Redis keys ──
_K_SHIFT = "nf:shift:{channel}"         # Hash: worker state per channel
_K_ACTIVITY = "nf:shift_activity:{channel}"  # String: last action timestamp
_K_TAKEOVER = "nf:shift_takeover:{channel}"  # String: JSON takeover request

# ── Constants ──
AFK_TIMEOUT_SECONDS = 45 * 60  # 45 minutes
SUPPORTED_CHANNELS = ("logcc", "thumbcc")


@dataclass
class ShiftState:
    """Current state of a channel's shift."""
    channel: str                        # "logcc" | "thumbcc"
    worker_id: int | None = None        # Telegram user id on duty
    worker_name: str = ""               # Display name
    started_at: float = 0.0             # Unix timestamp
    status: ShiftStatus = ShiftStatus.AVAILABLE
    takeover_requester_id: int | None = None
    takeover_requester_name: str = ""


@dataclass
class HandoffSummary:
    """Context passed to the new worker upon takeover."""
    channel: str
    previous_worker: str
    pending_count: int = 0
    active_count: int = 0
    completed_today: int = 0
    notes: str = ""
    started_at: float = 0.0


class ShiftService:
    """Manages the admin duty rotation for operational channels."""

    def __init__(self, container: Container) -> None:
        self._c = container

    # ── helpers ───────────────────────────────────────────────────────────

    @property
    def _redis(self):
        return self._c.redis

    def _active(self) -> bool:
        return self._redis is not None

    def _owner_ids(self) -> set[int]:
        """Owner telegram ids — they always bypass the shift system."""
        from nekofetch.services.auth_service import AuthService
        return AuthService(self._c).owner_ids()

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def get_state(self, channel: str) -> ShiftState:
        """Read the current shift state from Redis."""
        if not self._active():
            return ShiftState(channel=channel)
        raw = await self._redis.get(_K_SHIFT.format(channel=channel))
        if not raw:
            return ShiftState(channel=channel)
        try:
            data = json.loads(raw)
            return ShiftState(
                channel=channel,
                worker_id=data.get("worker_id"),
                worker_name=data.get("worker_name", ""),
                started_at=data.get("started_at", 0),
                status=ShiftStatus(data.get("status", "available")),
                takeover_requester_id=data.get("takeover_requester_id"),
                takeover_requester_name=data.get("takeover_requester_name", ""),
            )
        except (json.JSONDecodeError, ValueError):
            return ShiftState(channel=channel)

    async def _save_state(self, state: ShiftState) -> None:
        """Persist shift state to Redis."""
        if not self._active():
            return
        await self._redis.set(_K_SHIFT.format(channel=state.channel), json.dumps({
            "worker_id": state.worker_id,
            "worker_name": state.worker_name,
            "started_at": state.started_at,
            "status": state.status.value,
            "takeover_requester_id": state.takeover_requester_id,
            "takeover_requester_name": state.takeover_requester_name,
        }))

    async def touch_activity(self, channel: str) -> None:
        """Record that the current worker just performed an action."""
        if not self._active():
            return
        await self._redis.set(
            _K_ACTIVITY.format(channel=channel), str(time.time()), ex=AFK_TIMEOUT_SECONDS + 300
        )

    async def is_afk(self, channel: str) -> bool:
        """Check if the current worker has been inactive too long."""
        if not self._active():
            return False
        raw = await self._redis.get(_K_ACTIVITY.format(channel=channel))
        if not raw:
            return False
        last = float(raw)
        return (time.time() - last) > AFK_TIMEOUT_SECONDS

    # ── permission gate ───────────────────────────────────────────────────

    async def can_act(self, channel: str, user_id: int) -> tuple[bool, str]:
        """Check if a user can perform actions on a channel.

        Returns ``(allowed, reason)``. The owner always returns True.
        When allowed, the user is auto-assigned if the channel is available.
        """
        if user_id in self._owner_ids():
            # Owner always allowed — auto-take the shift if someone else is on it.
            state = await self.get_state(channel)
            if state.worker_id and state.worker_id != user_id:
                state.worker_id = user_id
                state.started_at = time.time()
                state.status = ShiftStatus.ACTIVE
                state.takeover_requester_id = None
                state.takeover_requester_name = ""
                await self._save_state(state)
            elif not state.worker_id:
                # Owner auto-assign when channel is unstaffed
                from nekofetch.services.auth_service import AuthService
                auth = AuthService(self._c)
                state.worker_id = user_id
                state.started_at = time.time()
                state.status = ShiftStatus.ACTIVE
                state.worker_name = ""  # resolved by caller
                await self._save_state(state)
            await self.touch_activity(channel)
            return True, "owner"

        state = await self.get_state(channel)
        # Channel is available — auto-assign
        if state.worker_id is None:
            state.worker_id = user_id
            state.started_at = time.time()
            state.status = ShiftStatus.ACTIVE
            await self._save_state(state)
            await self.touch_activity(channel)
            return True, "assigned"

        # Current worker — allow
        if state.worker_id == user_id:
            await self.touch_activity(channel)
            return True, "on_duty"

        # Someone else is on duty
        name = state.worker_name or f"Admin {state.worker_id}"
        return False, name

    # ── assign / release ──────────────────────────────────────────────────

    async def assign(self, channel: str, user_id: int, user_name: str = "") -> ShiftState:
        """Force-assign a user to the shift."""
        state = ShiftState(
            channel=channel,
            worker_id=user_id,
            worker_name=user_name,
            started_at=time.time(),
            status=ShiftStatus.ACTIVE,
        )
        await self._save_state(state)
        await self.touch_activity(channel)
        log.info("shift.assigned", channel=channel, user=user_id, name=user_name)
        return state

    async def release(self, channel: str, *, forced: bool = False) -> ShiftState:
        """Release the current shift, making the channel available."""
        old = await self.get_state(channel)
        state = ShiftState(channel=channel)
        await self._save_state(state)
        if self._active():
            await self._redis.delete(_K_ACTIVITY.format(channel=channel))
            await self._redis.delete(_K_TAKEOVER.format(channel=channel))
        log.info("shift.released", channel=channel, forced=forced,
                 previous_worker=old.worker_id)
        return state

    async def auto_release_if_afk(self, channel: str) -> ShiftState | None:
        """Release the shift if the current worker is AFK, returning the new state."""
        state = await self.get_state(channel)
        if state.worker_id is None:
            return None
        if await self.is_afk(channel):
            old_id = state.worker_id
            new_state = await self.release(channel, forced=True)
            log.info("shift.afk_released", channel=channel,
                     worker=old_id, name=state.worker_name)
            return new_state
        return None

    # ── takeover flow ─────────────────────────────────────────────────────

    async def request_takeover(
        self, channel: str, requester_id: int, requester_name: str,
    ) -> ShiftState | None:
        """Admin B requests to take over the shift from Admin A."""
        state = await self.get_state(channel)
        if state.worker_id is None or state.worker_id == requester_id:
            return None  # No one to request from, or requesting self
        state.status = ShiftStatus.TAKEOVER_PENDING
        state.takeover_requester_id = requester_id
        state.takeover_requester_name = requester_name
        await self._save_state(state)
        if self._active():
            await self._redis.set(
                _K_TAKEOVER.format(channel=channel),
                json.dumps({
                    "requester_id": requester_id,
                    "requester_name": requester_name,
                    "worker_id": state.worker_id,
                }),
                ex=600,  # 10 min TTL — request expires
            )
        log.info("shift.takeover_requested", channel=channel,
                 requester=requester_id, worker=state.worker_id)
        return state

    async def approve_takeover(
        self, channel: str, worker_id: int,
    ) -> tuple[bool, ShiftState | None, int | None]:
        """Current worker approves the takeover. Returns (ok, new_state, requester_id)."""
        state = await self.get_state(channel)
        if state.worker_id != worker_id:
            return False, None, None
        if state.status != ShiftStatus.TAKEOVER_PENDING:
            return False, None, None
        requester_id = state.takeover_requester_id
        requester_name = state.takeover_requester_name
        if not requester_id:
            return False, None, None
        # Transfer shift
        new_state = ShiftState(
            channel=channel,
            worker_id=requester_id,
            worker_name=requester_name,
            started_at=time.time(),
            status=ShiftStatus.ACTIVE,
        )
        await self._save_state(new_state)
        await self.touch_activity(channel)
        if self._active():
            await self._redis.delete(_K_TAKEOVER.format(channel=channel))
        log.info("shift.takeover_approved", channel=channel,
                 from_worker=worker_id, to_worker=requester_id)
        return True, new_state, requester_id

    async def deny_takeover(self, channel: str, worker_id: int) -> int | None:
        """Current worker denies the takeover. Returns requester_id to notify."""
        state = await self.get_state(channel)
        if state.worker_id != worker_id:
            return None
        if state.status != ShiftStatus.TAKEOVER_PENDING:
            return None
        requester_id = state.takeover_requester_id
        # Reset to active
        state.status = ShiftStatus.ACTIVE
        state.takeover_requester_id = None
        state.takeover_requester_name = ""
        await self._save_state(state)
        if self._active():
            await self._redis.delete(_K_TAKEOVER.format(channel=channel))
        log.info("shift.takeover_denied", channel=channel,
                 worker=worker_id, requester=requester_id)
        return requester_id

    # ── relief flow ───────────────────────────────────────────────────────

    async def seek_relief(self, channel: str, worker_id: int) -> ShiftState | None:
        """Current worker requests relief."""
        state = await self.get_state(channel)
        if state.worker_id != worker_id:
            return None
        state.status = ShiftStatus.RELIEF_SOUGHT
        await self._save_state(state)
        log.info("shift.relief_sought", channel=channel, worker=worker_id)
        return state

    async def accept_relief(
        self, channel: str, acceptor_id: int, acceptor_name: str,
    ) -> tuple[bool, ShiftState | None, int | None]:
        """An off-duty admin accepts the relief request. First to accept wins."""
        state = await self.get_state(channel)
        if state.status != ShiftStatus.RELIEF_SOUGHT:
            return False, None, None
        if state.worker_id == acceptor_id:
            return False, None, None  # Can't relieve yourself
        old_worker_id = state.worker_id
        # Transfer shift
        new_state = ShiftState(
            channel=channel,
            worker_id=acceptor_id,
            worker_name=acceptor_name,
            started_at=time.time(),
            status=ShiftStatus.ACTIVE,
        )
        await self._save_state(new_state)
        await self.touch_activity(channel)
        log.info("shift.relief_accepted", channel=channel,
                 from_worker=old_worker_id, to_worker=acceptor_id)
        return True, new_state, old_worker_id

    # ── handoff summary ───────────────────────────────────────────────────

    async def build_handoff_summary(self, channel: str, notes: str = "") -> HandoffSummary:
        """Build a status summary for the incoming worker."""
        from nekofetch.services.request_service import RequestService
        from nekofetch.services.queue_service import QueueService

        state = await self.get_state(channel)
        pending = 0
        try:
            reqs = await RequestService(self._c).list_pending(limit=50)
            pending = len(reqs)
        except Exception:
            pass

        active = 0
        try:
            qrows = await QueueService(self._c).dashboard(limit=20)
            active = len(qrows)
        except Exception:
            pass

        return HandoffSummary(
            channel=channel,
            previous_worker=state.worker_name or str(state.worker_id or "—"),
            pending_count=pending,
            active_count=active,
            notes=notes,
            started_at=state.started_at,
        )

    # ── staff list ────────────────────────────────────────────────────────

    async def list_staff_ids(self) -> list[dict]:
        """Return all staff+admins (but not owner, since owner always bypasses)."""
        from nekofetch.services.staff_service import StaffService

        owner_ids = self._owner_ids()
        members = await StaffService(self._c).list_team()
        return [
            {"telegram_id": m.telegram_id, "name": m.name, "role": m.role}
            for m in members
            if m.telegram_id not in owner_ids and not m.banned
        ]
