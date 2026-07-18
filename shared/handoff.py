"""Pipeline stage handoff — fire the next admin card when a stage finishes.

Kuro Sōden runs four bots as a relay: Lelouch (request) → Levi (download) →
Senku (distribution) → Gojo (publish). Each stage, when it finishes, must hand
the request to the next stage's admin. Lelouch already does this inline after a
submit; this module provides the *download → distribution* handoff, wired into
NekoFetch's download worker through the optional ``container.on_download_complete``
hook (set by :class:`PipelineManager`).

The handoff is best-effort: it records the DB assignment and DMs every admin via
Senku's client (falling back to any live client). A blocked DM or a missing bot
never fails the download job — the request still advanced in the DB.
"""

from __future__ import annotations

import html

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.ui.components import cb

log = get_logger(__name__)


async def handoff_download_to_distribution(
    container: Container, code: str, title: str,
) -> None:
    """Assign the distribution stage and DM admins that a title is ready.

    Called by the download worker via ``container.on_download_complete`` once a
    request's files are downloaded, processed, and stored.
    """
    # ── 1. Record the DB assignment (best-effort) ──────────────────────────
    try:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        await engine.complete_task(code, "levi")
        await engine.assign(code, "senku")
    except Exception as exc:  # noqa: BLE001
        log.warning("handoff.assign.failed", code=code, error=str(exc))

    # ── 2. DM every admin via Senku (the stage that acts next) ─────────────
    admin_ids = list(getattr(container.env, "admin_ids", []) or [])
    if not admin_ids:
        log.warning("handoff.no_admins", code=code)
        return

    notifier = None
    mgr = getattr(container, "pipeline_manager", None)
    if mgr is not None:
        notifier = getattr(mgr, "senku", None) or getattr(mgr, "levi", None)
    if notifier is None:
        log.warning("handoff.no_notifier", code=code)
        return

    caption = (
        "<b>📦 Ready for Distribution</b>\n\n"
        f"<b>{html.escape(title or code)}</b>\n"
        f"<code>{code}</code>\n\n"
        "<i>Downloaded and processed. Open Senku to create the distribution "
        "channel and generate its content.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🧪 Open Distribution", callback_data=cb("senku", "wiz", "open", code))],
    ])

    # Rotating artwork from this anime's own gallery — the handoff card carries
    # the series' art, continuing the "every card for this anime shows its art"
    # thread from the request receipt through the pipeline.
    image = await _handoff_art(container, code, title)

    sent = 0
    for admin_id in admin_ids:
        try:
            if image is not None:
                await notifier.send_photo(
                    admin_id, image, caption=caption,
                    parse_mode=ParseMode.HTML, reply_markup=kb,
                )
            else:
                await notifier.send_message(
                    admin_id, caption, parse_mode=ParseMode.HTML, reply_markup=kb,
                )
            sent += 1
        except Exception as exc:  # noqa: BLE001 - one blocked admin can't stop the rest
            log.warning("handoff.dm_failed", admin=admin_id, code=code, error=str(exc))
    log.info("handoff.sent", code=code, admins=len(admin_ids), delivered=sent)


async def _handoff_art(container: Container, code: str, title: str) -> str | None:
    """Resolve this anime's rotating artwork for the handoff card, or ``None``.

    Pulls the request's persisted franchise (seeded backdrops) and asks the
    per-anime pool for the next piece; best-effort, never raises.
    """
    try:
        from nekofetch.services.request_service import RequestService
        from nekofetch.ui.artwork import (
            ensure_anime_art, key_for_franchise, next_anime_art,
        )

        req = await RequestService(container).get(code)
        franchise = req.franchise_data or {}
        art_title = franchise.get("title") or req.anime_title or title
        key = key_for_franchise(franchise, title=art_title)
        await ensure_anime_art(key, tmdb=container.tmdb, title=art_title,
                               franchise=franchise)
        art = next_anime_art(key)
        return art if isinstance(art, str) else None
    except Exception as exc:  # noqa: BLE001 — artwork is decorative
        log.warning("handoff.art.failed", code=code, error=str(exc))
        return None
