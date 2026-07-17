"""Levi handler registration.

Reuses NekoFetch's existing download infrastructure:
  • DownloadWorker — background loop picks up QUEUED jobs automatically.
  • QueueService — enqueues jobs for the worker.
  • ProcessingPipeline — runs after downloads complete.
  • SourceRegistry — lists available sources for admin selection.

Levi's role is manual source selection + download queuing — the heavy lifting
is all done by NekoFetch's existing services.
"""

from __future__ import annotations

from pyrogram import Client

from nekofetch.core.container import Container


def register_all(client: Client, container: Container) -> None:
    """Wire all Levi handlers — reuses NekoFetch's download infrastructure."""

    # ── Auth middleware ────────────────────────────────────────────────────
    from nekofetch.bots.middleware import install_auth_middleware

    install_auth_middleware(client, container)

    # ── Levi task handlers (source selection, download queuing) ────────────
    from kurosoden.bots.levi.handlers.tasks import register as register_tasks

    register_tasks(client, container)
