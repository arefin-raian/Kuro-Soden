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
    """Wire all Levi handlers — reuses NekoFetch's download infrastructure.

    The real source-pick → website-report → torrent-picker → franchise-map →
    queue flow lives in NekoFetch's admin ``review`` handler. That admin bot is
    never started in the Kuro Sōden pipeline, so the flow would otherwise be dead
    code — we mount it directly onto Levi (the downloader stage that owns source
    selection) and route Levi's task cards into it via ``staff|rdetail|<code>``.
    Its callbacks use ``staff|`` / ``franchise|`` / ``anizone|`` prefixes and its
    message handlers use explicit ``group=`` slots, so nothing collides with
    Levi's own ``levi|`` menu or default-group photo handler.
    """

    # ── Auth middleware ────────────────────────────────────────────────────
    from nekofetch.bots.middleware import install_auth_middleware

    install_auth_middleware(client, container)

    # ── The full download/source machinery (mounted from admin.review) ─────
    from nekofetch.bots.admin.handlers import review

    review.register(client, container)

    # ── Levi's native config-driven settings panel (levi|set|…) ────────────
    # Registered before the app.py `levi|` fallback so every settings tap is
    # handled here. Replaces the old static /dlset-style screens.
    from kurosoden.bots.levi.handlers.settings import register as register_settings

    register_settings(client, container)

    # ── Levi task handlers (task list → routes into the review flow) ───────
    from kurosoden.bots.levi.handlers.tasks import register as register_tasks

    register_tasks(client, container)
