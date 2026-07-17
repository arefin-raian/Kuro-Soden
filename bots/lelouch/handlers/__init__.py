"""Lelouch handler registration.

Reuses NekoFetch's existing module-level request helpers
(``_media_to_franchise_dict``, ``apply_franchise_totals``, ``enrich_with_tmdb``)
and registers Lelouch-specific handlers that add:
  • Duplicate detection (main channel → distribution → in-progress).
  • One-request-at-a-time limit for regular users.
  • Admin assignment after submission.
"""

from __future__ import annotations

from pyrogram import Client

from nekofetch.core.container import Container


def register_all(client: Client, container: Container) -> None:
    """Wire all Lelouch handlers — reuses NekoFetch's existing request flow."""

    # ── Auth middleware (same as NekoFetch's admin bot) ───────────────────
    from nekofetch.bots.middleware import install_auth_middleware

    install_auth_middleware(client, container)

    # ── NekoFetch's existing batch handler (admin batch requests) ────────
    from nekofetch.bots.admin.handlers.batch import register as register_batch

    register_batch(client, container)

    # ── Lelouch request handlers ─────────────────────────────────────────
    from kurosoden.bots.lelouch.handlers.requests import register as register_requests

    register_requests(client, container)
