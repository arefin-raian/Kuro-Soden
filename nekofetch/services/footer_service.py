"""Universal footer edit — rewrite the distribution footer across every channel.

The distribution footer is delivered on ``/start`` from stored
:class:`BotContentPost` rows (``post_type == "footer"``), not from a live channel
message, so "editing the footer everywhere" means three things done atomically:

1. update ``config.bot.footer_text`` so every *future* generated post uses it;
2. rewrite the ``caption`` of every existing footer row in the DB; and
3. bump each affected bot's ``content_revision`` so returning users get the new
   footer re-delivered on their next ``/start`` (the delete-then-redeliver dance
   keyed on ``BotDelivery.delivered_revision``).

The incoming text is run through :func:`parse_user_markup` so an admin can paste
Telegram-native styling, HTML, or Markdown and get correct HTML stored.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.infrastructure.database.postgres.models import (
    BotContentPost,
    DistributionBot,
)
from nekofetch.infrastructure.database.postgres.session import session_scope

log = get_logger(__name__)


@dataclass(slots=True)
class FooterEditResult:
    footers_rewritten: int   # BotContentPost rows updated
    bots_bumped: int         # distinct bots whose content_revision advanced
    ok: bool = True


class FooterService:
    def __init__(self, container: Container) -> None:
        self._c = container

    async def set_footer(self, html: str) -> FooterEditResult:
        """Apply ``html`` as the footer everywhere.

        ``html`` must already be the final stored HTML — the caller runs the
        admin's message through :func:`parse_user_markup` so Telegram-native
        styling / Markdown / hand-typed HTML all normalise the same way the
        caption editor does. Returns a :class:`FooterEditResult` tallying the
        rewrite; best-effort on the config write (a missing SettingsService
        still updates the DB rows).
        """
        html = (html or "").strip()
        if not html:
            return FooterEditResult(0, 0, ok=False)

        # 1. Future posts: persist the new footer template on config.bot.
        try:
            from nekofetch.services.settings_service import SettingsService

            await SettingsService(self._c).set_value("bot", "footer_text", html)
        except Exception as exc:  # noqa: BLE001 — DB rewrite still proceeds
            log.warning("footer.config_write_failed", error=str(exc))

        # 2 + 3. Existing footer rows + revision bumps, in one transaction.
        async with session_scope(self._c.pg_sessionmaker) as session:
            footer_rows = (
                await session.execute(
                    select(BotContentPost).where(BotContentPost.post_type == "footer")
                )
            ).scalars().all()

            bot_ids = {row.bot_id for row in footer_rows}
            for row in footer_rows:
                row.caption = html

            if bot_ids:
                await session.execute(
                    update(DistributionBot)
                    .where(DistributionBot.id.in_(bot_ids))
                    .values(content_revision=DistributionBot.content_revision + 1)
                )
            await session.commit()

        log.info("footer.updated", footers=len(footer_rows), bots=len(bot_ids))
        return FooterEditResult(len(footer_rows), len(bot_ids))
