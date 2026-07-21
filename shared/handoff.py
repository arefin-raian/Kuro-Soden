"""Pipeline stage handoff and stage-specific staff notifications."""

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
    """Complete Levi, assign Senku, then send the distribution card."""
    try:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        await engine.complete_task(code, "levi")
        assignment = await engine.assign(code, "senku")
    except Exception as exc:  # noqa: BLE001
        log.warning("handoff.assign.failed", code=code, error=str(exc))
        assignment = None
    if assignment is None:
        log.info("handoff.deferred_or_unassigned", code=code, stage="senku")
        return

    await notify_stage_assignment(container, "senku", assignment, code, title)


async def handoff_distribution_to_publish(
    container: Container, code: str, title: str,
) -> None:
    """Complete Senku, assign Gojo, then send the publishing card."""
    try:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        await engine.complete_task(code, "senku")
        assignment = await engine.assign(code, "gojo")
    except Exception as exc:  # noqa: BLE001
        log.warning("handoff.publish.assign.failed", code=code, error=str(exc))
        assignment = None
    if assignment is None:
        log.info("handoff.publish.deferred_or_unassigned", code=code, stage="gojo")
        return

    await notify_stage_assignment(container, "gojo", assignment, code, title)


async def notify_stage_assignment(
    container: Container,
    stage: str,
    assignment,
    code: str,
    title: str,
    *,
    requester: str | None = None,
    requester_id: int | None = None,
    franchise_json: dict | None = None,
) -> int:
    """Send one stage-specific assignment or offer card with this anime's backdrop."""
    admin_id = int(assignment.admin_telegram_id)
    notifier = _stage_notifier(container, stage)
    if notifier is None:
        log.warning("handoff.notify.no_notifier", code=code, stage=stage)
        return 0

    caption = _stage_caption(
        stage, assignment, code, title, requester, requester_id, franchise_json
    )
    keyboard = _stage_keyboard(stage, assignment, code)
    image = await _stage_art(container, code, title, franchise_json)

    try:
        if image is not None:
            await notifier.send_photo(
                admin_id, image, caption=caption,
                parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
        else:
            await notifier.send_message(
                admin_id, caption, parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
        log.info("handoff.notify.sent", code=code, stage=stage, admin=admin_id)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.warning("handoff.notify.photo_failed", code=code, stage=stage,
                    admin=admin_id, error=str(exc))
        try:
            await notifier.send_message(
                admin_id, caption, parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
            log.info("handoff.notify.sent_text", code=code, stage=stage, admin=admin_id)
            return 1
        except Exception as exc2:  # noqa: BLE001
            log.warning("handoff.notify.dm_failed", code=code, stage=stage,
                        admin=admin_id, error=str(exc2))
            return 0


def _stage_notifier(container: Container, stage: str):
    mgr = getattr(container, "pipeline_manager", None)
    if mgr is None:
        return None
    if stage == "levi":
        return getattr(mgr, "levi", None) or getattr(mgr, "lelouch", None)
    if stage == "senku":
        return getattr(mgr, "senku", None) or getattr(mgr, "levi", None)
    if stage == "gojo":
        return getattr(mgr, "gojo", None) or getattr(mgr, "senku", None)
    return None


def _stage_caption(
    stage: str,
    assignment,
    code: str,
    title: str,
    requester: str | None,
    requester_id: int | None,
    franchise_json: dict | None,
) -> str:
    escaped_title = html.escape(title or code)
    is_offer = getattr(assignment, "status", "assigned") == "offered"
    if stage == "levi":
        who = ""
        if requester_id is not None:
            who = (
                f"\n👤 <b>By:</b> {html.escape(requester or 'user')} "
                f"(<code>{requester_id}</code>)\n"
            )
        header = "⚔️ Levi Offer" if is_offer else "⚔️ New Download Task"
        body = (
            "You were active during quiet hours, so this is optional. "
            "Accept it or leave it for the next slot."
            if is_offer else
            "Assigned to download. Open Levi, pick the source, and cut the queue clean."
        )
        return (
            f"<b>{header}</b>\n\n"
            f"<b>{escaped_title}</b>\n"
            f"<code>{code}</code> · {_franchise_bits(franchise_json or {})}{who}\n"
            f"<i>{body}</i>"
        )
    if stage == "senku":
        header = "🧪 Senku Offer" if is_offer else "🧪 Ready for Distribution"
        body = (
            "This landed outside your slot while you were active. Accept to build it now, "
            "or reject and let the ladder move."
            if is_offer else
            "Downloaded, processed, and ready for the channel build. Open the wizard."
        )
        return f"<b>{header}</b>\n\n<b>{escaped_title}</b>\n<code>{code}</code>\n\n<i>{body}</i>"
    header = "🔮 Gojo Offer" if is_offer else "🔮 Ready to Publish"
    body = (
        "Optional publish review. Accept it if you are taking the slot now."
        if is_offer else
        f"Distribution is complete. Run <code>/publish {html.escape(code)}</code> "
        "to review the main-channel post and go live."
    )
    return f"<b>{header}</b>\n\n<b>{escaped_title}</b>\n<code>{code}</code>\n\n<i>{body}</i>"


def _stage_keyboard(stage: str, assignment, code: str) -> InlineKeyboardMarkup:
    is_offer = getattr(assignment, "status", "assigned") == "offered"
    if is_offer:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Accept", callback_data=cb(stage, "offer", "accept", code)),
                InlineKeyboardButton("Reject", callback_data=cb(stage, "offer", "reject", code)),
            ],
            [InlineKeyboardButton("📋 Open Tasks", callback_data=cb(stage, "tasks"))],
        ])
    if stage == "levi":
        rows = [[InlineKeyboardButton("📋 Open Download Tasks", callback_data=cb("levi", "tasks"))]]
    elif stage == "senku":
        rows = [[
            InlineKeyboardButton(
                "🧪 Open Distribution",
                callback_data=cb("senku", "wiz", "open", code),
            ),
        ]]
    else:
        rows = [[
            InlineKeyboardButton(
                "📋 Open Publishing Tasks",
                callback_data=cb("gojo", "tasks"),
            ),
        ]]
    return InlineKeyboardMarkup(rows)


def _franchise_bits(franchise_json: dict) -> str:
    bits = []
    for key, label in (
        ("franchise_seasons", "season"),
        ("franchise_movies", "movie"),
        ("franchise_ovas", "OVA"),
    ):
        count = int(franchise_json.get(key) or 0)
        if count:
            plural = "" if count == 1 or label == "OVA" else "s"
            bits.append(f"{count} {label}{plural}")
    return " · ".join(bits) if bits else "single entry"


async def _stage_art(
    container: Container, code: str, title: str, franchise_json: dict | None
) -> str | None:
    if franchise_json:
        direct = franchise_json.get("_backdrop_url") or franchise_json.get("banner_url")
        if isinstance(direct, str) and direct:
            return direct
        gallery = franchise_json.get("backdrops") or []
        for item in gallery:
            if isinstance(item, str) and item:
                return item
    return await _handoff_art(container, code, title)


async def _handoff_art(container: Container, code: str, title: str) -> str | None:
    """Resolve this anime's rotating artwork for the handoff card."""
    try:
        from nekofetch.services.request_service import RequestService
        from nekofetch.ui.artwork import ensure_anime_art, key_for_franchise, next_anime_art

        req = await RequestService(container).get(code)
        franchise = req.franchise_data or {}
        art_title = franchise.get("title") or req.anime_title or title
        key = key_for_franchise(franchise, title=art_title)
        await ensure_anime_art(key, tmdb=container.tmdb, title=art_title,
                               franchise=franchise)
        art = next_anime_art(key)
        return art if isinstance(art, str) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("handoff.art.failed", code=code, error=str(exc))
        return None
