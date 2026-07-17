"""PipelineManager — starts and supervises all four pipeline bots.

Modeled after NekoFetch's BotManager but designed for the multi-bot pipeline
where each bot watches the database for work in its stage of the request lifecycle.

Architecture:
    PipelineManager
       ├── Lelouch  (Request Bot)    —  REQUEST_BOT_TOKEN
       ├── Levi     (Downloader Bot) —  DOWNLOADER_BOT_TOKEN
       ├── Senku    (Distribution)   —  DISTRIBUTION_BOT_TOKEN
       └── Gojo     (Publisher)      —  PUBLISHER_BOT_TOKEN

Bots communicate through shared DB state (requests.status transitions), not
through direct inter-bot messaging. Each bot polls for rows in its relevant
status and picks them up when an admin is assigned.
"""

from __future__ import annotations

import asyncio
from typing import Any

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

log = get_logger(__name__)

# Connection watchdog intervals (mirrors BotManager's approach).
_CONN_CHECK_INTERVAL = 30
_CONN_PROBE_TIMEOUT = 20
_CONN_RECONNECT_ATTEMPTS = 3
_CONN_RECONNECT_TIMEOUT = 60
_CONN_RECONNECT_BACKOFF = 5


class PipelineManager:
    """Manages the lifecycle of all four pipeline bots on one event loop."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self._clients: dict[str, Any] = {}  # name → Pyrogram Client
        self._conn_watchdog_task: asyncio.Task | None = None
        self._scheduler = None

    async def start(self) -> None:
        """Start all pipeline bots. Order: Lelouch → Levi → Senku → Gojo."""
        from nekofetch.infrastructure.scheduler import Scheduler

        self._c.pipeline_manager = self  # type: ignore[attr-defined]

        # Wire the download → distribution handoff. NekoFetch's download worker
        # fires this hook when a job finishes; we hand the request to Senku.
        from kurosoden.shared.handoff import handoff_download_to_distribution

        async def _on_download_complete(code: str, title: str) -> None:
            await handoff_download_to_distribution(self._c, code, title)

        self._c.on_download_complete = _on_download_complete  # type: ignore[attr-defined]

        # ── 1. Lelouch — Request Bot ──────────────────────────────────────────
        await self._start_bot("lelouch", "REQUEST_BOT_TOKEN")

        # ── 2. Levi — Downloader Bot ──────────────────────────────────────────
        await self._start_bot("levi", "DOWNLOADER_BOT_TOKEN")

        # ── 3. Senku — Distribution Bot ───────────────────────────────────────
        await self._start_bot("senku", "DISTRIBUTION_BOT_TOKEN")

        # ── 4. Gojo — Publisher Bot ───────────────────────────────────────────
        await self._start_bot("gojo", "PUBLISHER_BOT_TOKEN")

        # ── Scheduler for background tasks ────────────────────────────────────
        self._scheduler = Scheduler()
        self._c.scheduler = self._scheduler  # type: ignore[attr-defined]
        self._scheduler.start()

        # ── Connection watchdog ───────────────────────────────────────────────
        self._conn_watchdog_task = asyncio.create_task(self._connection_watchdog())

        log.info("kuro-soden.pipeline.started", bots=list(self._clients.keys()))

    async def _start_bot(self, name: str, env_var: str) -> None:
        """Start a single pipeline bot by name."""
        import os

        token = os.getenv(env_var, "").strip()
        if not token:
            log.warning("kuro-soden.bot.token_missing", bot=name, env_var=env_var,
                        hint=f"Set {env_var} in .env to enable the {name} bot")
            return

        try:
            if name == "lelouch":
                from kurosoden.bots.lelouch.app import build_lelouch, publish_commands
                client = build_lelouch(self._c, token)
            elif name == "levi":
                from kurosoden.bots.levi.app import build_levi, publish_commands
                client = build_levi(self._c, token)
            elif name == "senku":
                from kurosoden.bots.senku.app import build_senku, publish_commands
                client = build_senku(self._c, token)
            elif name == "gojo":
                from kurosoden.bots.gojo.app import build_gojo, publish_commands
                client = build_gojo(self._c, token)
            else:
                log.error("kuro-soden.bot.unknown", name=name)
                return

            await client.start()
            self._clients[name] = client
            # Populate the Telegram burger-menu command list (best-effort — a
            # failed set_bot_commands must never stop the bot from running).
            try:
                await publish_commands(client)
            except Exception as exc:  # noqa: BLE001
                log.warning("kuro-soden.bot.commands_failed", bot=name, error=str(exc))
            log.info("kuro-soden.bot.started", bot=name)
        except Exception as exc:
            log.error("kuro-soden.bot.start_failed", bot=name, error=str(exc))

    @property
    def lelouch(self):
        """Return the Lelouch (Request Bot) Pyrogram client."""
        return self._clients.get("lelouch")

    @property
    def levi(self):
        """Return the Levi (Downloader Bot) Pyrogram client."""
        return self._clients.get("levi")

    @property
    def senku(self):
        """Return the Senku (Distribution Bot) Pyrogram client."""
        return self._clients.get("senku")

    @property
    def gojo(self):
        """Return the Gojo (Publisher Bot) Pyrogram client."""
        return self._clients.get("gojo")

    # ── connection watchdog ──────────────────────────────────────────────────

    async def _connection_watchdog(self) -> None:
        """Detect dead Telegram links and force clean reconnects."""
        while True:
            try:
                await asyncio.sleep(_CONN_CHECK_INTERVAL)
                for name, client in list(self._clients.items()):
                    if client is None:
                        continue
                    try:
                        await asyncio.wait_for(client.get_me(), timeout=_CONN_PROBE_TIMEOUT)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        log.warning("kuro-soden.conn.probe_failed", bot=name, error=str(exc))
                        await self._reconnect_client(name, client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("kuro-soden.conn_watchdog.error", error=str(exc))

    async def _reconnect_client(self, name: str, client) -> bool:
        """Force a fresh Telegram session for a dead link."""
        for attempt in range(1, _CONN_RECONNECT_ATTEMPTS + 1):
            try:
                await asyncio.wait_for(client.restart(), timeout=_CONN_RECONNECT_TIMEOUT)
                log.info("kuro-soden.conn.reconnected", bot=name, attempt=attempt)
                return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("kuro-soden.conn.reconnect_failed", bot=name, attempt=attempt, error=str(exc))
                await asyncio.sleep(_CONN_RECONNECT_BACKOFF)
        log.error("kuro-soden.conn.reconnect_exhausted", bot=name)
        return False

    async def stop(self) -> None:
        """Gracefully stop all bots."""
        if self._scheduler is not None:
            self._scheduler.shutdown()
        if self._conn_watchdog_task is not None and not self._conn_watchdog_task.done():
            self._conn_watchdog_task.cancel()
        for name, client in self._clients.items():
            try:
                await client.stop()
                log.info("kuro-soden.bot.stopped", bot=name)
            except Exception:
                pass
        log.info("kuro-soden.pipeline.stopped")
