"""Senku handler registration.

Reuses NekoFetch's existing distribution infrastructure:
  • BotContentService — generates watch guides, info cards, season cards, footers.
  • BotFactory — creates distribution bots/channels.
  • BotOrchestratorService — orchestrates the full distribution flow.
"""

from __future__ import annotations

from pyrogram import Client
from nekofetch.core.container import Container


def register_all(client: Client, container: Container) -> None:
    from nekofetch.bots.middleware import install_auth_middleware
    from kurosoden.bots.senku.handlers.tasks import register as register_tasks
    from kurosoden.bots.senku.handlers.wizard import register as register_wizard

    install_auth_middleware(client, container)
    register_wizard(client, container)
    register_tasks(client, container)
