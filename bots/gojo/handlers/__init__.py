"""Gojo handler registration.

Reuses NekoFetch's existing publishing infrastructure:
  • MainChannelService — generates and posts to the main channel.
  • IndexChannelService — updates the A-Z index.
  • PublishingService — orchestrates the publish flow.
  • BotOrchestratorService — handles bot recreation for recovery.
"""

from __future__ import annotations

from pyrogram import Client
from nekofetch.core.container import Container


def register_all(client: Client, container: Container) -> None:
    from nekofetch.bots.middleware import install_auth_middleware
    from kage.bots.gojo.handlers.tasks import register as register_tasks

    install_auth_middleware(client, container)
    register_tasks(client, container)
