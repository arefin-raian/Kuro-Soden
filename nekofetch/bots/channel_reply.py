"""Channel-scoped awaited-reply marker.

Anonymous admins post in the Control Center **as the channel itself**, so their
messages arrive with no ``from_user`` — the per-user :class:`FSM` can't be keyed
to them. When a channel flow asks for a typed reply (AniZone slug mapping, a
franchise-mapping edit), we arm a marker keyed by **chat id** instead.

Two consumers read it:

* the channel guard checks :func:`is_armed` and, while a marker is live, leaves
  the next text message alone instead of deleting it on arrival — otherwise the
  guard would race the handler and eat the reply before it's ever read;
* the reply handler reads the stashed ``state`` + ``data`` to pick the flow back
  up, then calls :func:`disarm` so the channel goes back to being kept clean.

The marker carries the same small JSON bag the FSM would and expires on its own
TTL, so a half-finished flow never wedges the channel permanently.
"""

from __future__ import annotations

import json

from redis.asyncio import Redis

from nekofetch.core.constants import REDIS_CHANNEL_REPLY

# Same window the FSM uses (15 min) — long enough to find a slug in a browser,
# short enough that an abandoned flow un-arms itself.
_TTL = 900


def _key(chat_id: int) -> str:
    return REDIS_CHANNEL_REPLY.format(chat_id=chat_id)


async def arm(redis: Redis | None, chat_id: int, state: str, **data) -> None:
    """Arm the awaited-reply marker for ``chat_id`` with ``state`` + ``data``."""
    if redis is None:
        return
    await redis.set(_key(chat_id), json.dumps({"state": state, "data": data}), ex=_TTL)


async def peek(redis: Redis | None, chat_id: int) -> tuple[str | None, dict]:
    """Return ``(state, data)`` for ``chat_id``'s armed flow, or ``(None, {})``."""
    if redis is None:
        return None, {}
    raw = await redis.get(_key(chat_id))
    if not raw:
        return None, {}
    parsed = json.loads(raw)
    return parsed.get("state"), parsed.get("data", {})


async def disarm(redis: Redis | None, chat_id: int) -> None:
    """Clear the awaited-reply marker for ``chat_id`` (idempotent)."""
    if redis is None:
        return
    await redis.delete(_key(chat_id))


async def is_armed(redis: Redis | None, chat_id: int) -> bool:
    """Cheap existence check used by the channel guard on every message."""
    if redis is None:
        return False
    return bool(await redis.exists(_key(chat_id)))
