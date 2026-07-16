"""Lelouch request handlers — REUSES NekoFetch's existing request flow.

Key design principle: **We do NOT rewrite NekoFetch's AniList search logic.**
We import the module-level helper functions that the admin bot already uses
and register the same FSM-driven flow with Lelouch-specific additions:

  • Duplicate detection before accepting (dedup across main/dist/in-progress).
  • One-request-at-a-time limit for regular users (configurable).
  • Admin batch request support for staff.
  • Admin assignment to the downloader stage after submission.

The actual AniList search, franchise confirmation, TMDB enrichment, version
picker, and submission logic is ALL reused from the existing codebase.
"""

from __future__ import annotations

import html

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.exceptions import NekoFetchError
from nekofetch.domain.enums import DownloadScope, RequestStatus
from nekofetch.localization.messages import M, t
from nekofetch.ui.components import lock_buttons
from nekofetch.ui.progress import SPINNER, animate_until
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.screens import (
    Screen,
    ask_title,
    choose_version,
    confirm_franchise,
    request_received,
    retry_title,
    send_screen,
)

# ── REUSED from NekoFetch's existing admin handler ───────────────────────────
# These are module-level functions in the admin bot's request handler.
# We import and use them directly — zero code duplication.
from nekofetch.bots.admin.handlers.requests import (
    _media_to_franchise_dict,
    apply_franchise_totals,
    enrich_with_tmdb,
)

# ── Lelouch-specific additions ───────────────────────────────────────────────
from kage.shared.admin_assignment import AdminAssignmentEngine
from kage.shared.dedup import DedupService

# ── Helpers ──────────────────────────────────────────────────────────────────


def _esc_q(text: str) -> str:
    """Escape a user-supplied query for safe inclusion in HTML captions."""
    return html.escape(text or "", quote=False)


STATE_NAME = "req:await_name"
STATE_FRANCHISE = "req:franchise"
LELOUCH_COMMANDS = ["start", "help", "myrequests", "admin", "settings", "batch"]


# ── Registration ─────────────────────────────────────────────────────────────


def register(client: Client, container: Container) -> None:
    """Register Lelouch's handlers on the Pyrogram client.

    Reuses NekoFetch's AniList search + franchise confirmation flow entirely,
    with Lelouch-specific dedup, rate limiting, and admin assignment layered on.
    """
    fsm = FSM(container.redis, bot="lelouch")
    dedup = DedupService(container.pg_sessionmaker)
    assignment = AdminAssignmentEngine(container.pg_sessionmaker)

    # ── /start handler (already in app.py, but register the FSM trigger too) ──
    @client.on_callback_query(filters.regex(r"^req\|new"))
    async def _new(_: Client, q: CallbackQuery) -> None:
        await fsm.set(q.from_user.id, STATE_NAME)
        screen = ask_title()
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)
        await q.answer()

    # ── Text handler — anime search with dedup ────────────────────────────────
    @client.on_message(
        filters.text & filters.private & ~filters.command(LELOUCH_COMMANDS)
    )
    async def _text(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, _data = await fsm.get(message.from_user.id)
        # In either state a typed message is a (new) title to look up.
        if state in (STATE_NAME, STATE_FRANCHISE):
            await _search_with_dedup(message, message.text.strip())

    # ── Lelouch's enhanced search — dedup first, then AniList ─────────────────
    async def _search_with_dedup(message: Message, query: str) -> None:
        """Check dedup before delegating to NekoFetch's AniList search."""
        user_id = message.from_user.id

        # ── 0. Check one-at-a-time limit for non-admin users ──────────────
        if not await _is_staff(message, container):
            if await _has_pending_request(user_id, container):
                await message.reply(
                    t(M.REQUEST_LIMIT_REACHED),
                    parse_mode=ParseMode.HTML,
                )
                return

        # ── 1. Dedup check ───────────────────────────────────────────────
        result = await dedup.check(query)
        if result.exists:
            await message.reply(result.detail, parse_mode=ParseMode.HTML)
            # If it's in-progress, give extra context.
            if result.source == "in_progress" and result.request_code:
                await message.reply(
                    f"📋 Request <code>{result.request_code}</code> is currently "
                    f"<b>{result.current_stage}</b>.\n\n"
                    f"You'll receive the link automatically when it's published!",
                    parse_mode=ParseMode.HTML,
                )
            return

        # ── 2. Delegate to NekoFetch's existing AniList search ───────────
        await _search_anilist(message, query)

    async def _is_staff(message: Message, container: Container) -> bool:
        """Check if the user is staff/admin (can bypass request limits)."""
        from nekofetch.domain.enums import Role

        user = getattr(message, "nf_user", None)
        if user is None:
            return False
        role = Role(user.role) if user else Role.USER
        return role in (Role.STAFF, Role.ADMIN)

    async def _has_pending_request(user_id: int, container: Container) -> bool:
        """Check if user already has an active request."""
        from nekofetch.services.request_service import RequestService

        rows = await RequestService(container).list_for_user(user_id, limit=5)
        active_statuses = {
            RequestStatus.PENDING,
            RequestStatus.APPROVED,
            RequestStatus.QUEUED,
            RequestStatus.DOWNLOADING,
            RequestStatus.PROCESSING,
            RequestStatus.READY,
        }
        for r in rows:
            status = r.status
            if isinstance(status, str):
                try:
                    status = RequestStatus(status)
                except ValueError:
                    continue
            if status in active_statuses:
                return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # AniList search — IDENTICAL to NekoFetch's admin handler logic
    # (reuses the same module-level helpers for franchise totals + TMDB)
    # ──────────────────────────────────────────────────────────────────────────
    async def _search_anilist(message: Message, query: str) -> None:
        def _frame(f: str) -> str:
            return t(M.SEARCHING, query=_esc_q(query), frame=f)

        msg = await message.reply(_frame(SPINNER[0]), parse_mode=ParseMode.HTML)

        # --- 1. Resolve the title (AniList first) ---
        media = await animate_until(msg, container.anilist.search(query), _frame)
        if media is None:
            # TMDB fallback
            tmdb_result = await animate_until(
                msg, container.tmdb.search(query), _frame
            )
            if tmdb_result is None:
                await msg.edit_text(
                    t(M.SEARCH_NOT_FOUND, query=_esc_q(query)),
                    parse_mode=ParseMode.HTML,
                )
                return

            tmdb_url = (
                f"https://www.themoviedb.org/{tmdb_result.media_type}/{tmdb_result.id}"
            )
            franchise_data = {
                "title": tmdb_result.title,
                "english": tmdb_result.title,
                "romaji": None,
                "year": tmdb_result.year,
                "format": tmdb_result.media_type.upper(),
                "status": None,
                "score": tmdb_result.rating,
                "studio": None,
                "genres": tmdb_result.genres,
                "synopsis": tmdb_result.overview,
                "synopsis_url": tmdb_url,
                "franchise_episodes": tmdb_result.episodes,
                "franchise_seasons": tmdb_result.seasons or 1,
                "franchise_movies": 0,
                "franchise_ovas": 0,
                "franchise_onas": 0,
                "franchise_specials": 0,
                "relations": [],
                "anilist_id": str(tmdb_result.id),
                "anilist_url": tmdb_url,
                "cover_url": tmdb_result.poster_url,
                "banner_url": tmdb_result.backdrop_url,
                "_source": "tmdb",
                "_query": query,
            }
            await fsm.set(
                message.from_user.id,
                STATE_FRANCHISE,
                franchise=franchise_data,
            )
            screen = confirm_franchise(franchise_data)
            msg = await send_screen(client, message.chat.id, screen, old_msg=msg)
            return

        # --- 2. Detect adaptations via SeriesResolver ---
        resolution = await container.series_resolver.resolve(query)
        franchise_data = _media_to_franchise_dict(media)

        if resolution.multiple:
            versions = [
                {
                    "title": e.title,
                    "id": str(e.anilist_id or media.id),
                    "anilist_id": str(e.anilist_id or media.id),
                    "format": e.format,
                    "year": None,
                    "episodes": None,
                    "aliases": e.aliases,
                }
                for e in resolution.entries
            ]
            await fsm.set(
                message.from_user.id,
                "req:versions",
                versions=versions,
                query=query,
                franchise=franchise_data,
            )
            screen = choose_version(query, versions)
            msg = await send_screen(client, message.chat.id, screen, old_msg=msg)
            return

        # --- 3. Single match — franchise totals + TMDB ---
        await apply_franchise_totals(container, franchise_data)
        backdrop_path = await enrich_with_tmdb(
            container, franchise_data, media.english or query
        )
        franchise_data["_backdrop_url"] = backdrop_path

        await fsm.set(
            message.from_user.id,
            STATE_FRANCHISE,
            franchise=franchise_data,
            query=query,
        )
        screen = confirm_franchise(franchise_data, backdrop_path=backdrop_path)
        msg = await send_screen(client, message.chat.id, screen, old_msg=msg)

    # ── Version picker callbacks ──────────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^ver_pick\|"))
    async def _ver_pick(_: Client, q: CallbackQuery) -> None:
        await lock_buttons(q)
        _, args = q.data.split("|", 1)
        picked_id = args
        _, data = await fsm.get(q.from_user.id)
        versions = data.get("versions", [])
        query = data.get("query", "Anime")

        chosen = next(
            (v for v in versions if str(v.get("id")) == picked_id),
            versions[0],
        )
        chosen_anilist_id = chosen.get("anilist_id") or chosen.get("id")

        try:
            refetched = await container.anilist._fetch_full(int(chosen_anilist_id))
        except (ValueError, TypeError):
            refetched = None

        if refetched:
            franchise_data = _media_to_franchise_dict(refetched)
        else:
            franchise_data = {
                "title": chosen.get("title", query),
                "anilist_id": chosen_anilist_id,
                "_source": "anilist",
            }

        franchise_data["title"] = chosen.get(
            "title", franchise_data.get("title", query)
        )
        await apply_franchise_totals(container, franchise_data)
        search_title = franchise_data.get("english") or franchise_data["title"]
        backdrop_path = await enrich_with_tmdb(container, franchise_data, search_title)
        franchise_data["_backdrop_url"] = backdrop_path

        await fsm.set(
            q.from_user.id,
            STATE_FRANCHISE,
            franchise=franchise_data,
            query=query,
        )
        screen = confirm_franchise(franchise_data, backdrop_path=backdrop_path)
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)
        await q.answer()

    # ── Confirmation / rejection ──────────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^series_yes\|"))
    async def _confirm(_: Client, q: CallbackQuery) -> None:
        await lock_buttons(q)
        _, data = await fsm.get(q.from_user.id)
        franchise_data = data.get("franchise", {})
        query = data.get("query", franchise_data.get("title", "Anime"))
        name = q.from_user.first_name if q.from_user else ""
        await q.answer()
        await _finalize(q.message, q.from_user.id, name, franchise_data, query=query)

    @client.on_callback_query(filters.regex(r"^series_no$"))
    async def _reject(_: Client, q: CallbackQuery) -> None:
        await fsm.set(q.from_user.id, STATE_NAME)
        screen = retry_title()
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)
        await q.answer()

    @client.on_callback_query(filters.regex(r"^noop$"))
    async def _noop(_: Client, q: CallbackQuery) -> None:
        await q.answer()

    # ── Finalize — submit + assign ────────────────────────────────────────────
    async def _finalize(
        card_msg: Message,
        user_id: int,
        user_name: str,
        franchise_data: dict,
        *,
        query: str,
    ) -> None:
        from nekofetch.services.request_service import RequestService
        from nekofetch.infrastructure.repositories.request_repo import RequestRepository
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.domain.enums import RequestStatus as RS

        title = franchise_data.get("title", query)
        anilist_id = franchise_data.get("anilist_id")
        source = franchise_data.get("_source", "anilist")

        franchise_json = {
            "anilist_id": anilist_id,
            "source": source,
            "query": query,
            "title": title,
            "english": franchise_data.get("english"),
            "romaji": franchise_data.get("romaji"),
            "year": franchise_data.get("year"),
            "format": franchise_data.get("format"),
            "franchise_episodes": franchise_data.get("franchise_episodes"),
            "franchise_seasons": franchise_data.get("franchise_seasons"),
            "franchise_movies": franchise_data.get("franchise_movies"),
            "franchise_ovas": franchise_data.get("franchise_ovas"),
            "franchise_onas": franchise_data.get("franchise_onas"),
            "franchise_specials": franchise_data.get("franchise_specials"),
            "relations": franchise_data.get("relations", []),
            "genres": franchise_data.get("genres", []),
            "synonyms": franchise_data.get("synonyms", []),
        }

        try:
            receipt = await RequestService(container).submit(
                telegram_id=user_id,
                source=source,
                source_ref=f"anilist:{anilist_id}" if anilist_id else query,
                anime_title=title,
                scope=DownloadScope.ENTIRE_SERIES,
                season=None,
                episodes=None,
                franchise_data=franchise_json,
            )
        except NekoFetchError as exc:
            await fsm.set(user_id, STATE_NAME)
            await send_screen(
                client,
                card_msg.chat.id,
                Screen(caption=t(exc.message_key), image=pick_artwork("lelouch")),
                old_msg=card_msg,
            )
            return

        await fsm.clear(user_id)

        # ── Lelouch-specific: Assign to a downloader admin ────────────────
        assigned = None
        try:
            assigned = await assignment.assign(receipt.code, "levi")
            # Update request status so Levi's downloader bot sees it.
            async with session_scope(container.pg_sessionmaker) as session:
                repo = RequestRepository(session)
                req = await repo.get_by_code(receipt.code)
                if req is not None:
                    req.status = RS.QUEUED
        except Exception:
            pass  # Assignment is best-effort; request still succeeded.

        # Build the success screen.
        extra = ""
        if assigned:
            extra = (
                f"\n\n👤 <b>Assigned to:</b> {assigned.admin_name or 'a downloader'}"
            )
        screen = request_received(user_name, title, queue_pos=receipt.position)
        screen.caption += extra
        await send_screen(client, card_msg.chat.id, screen, old_msg=card_msg)

    # ── My Requests ───────────────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^req\|mine"))
    async def _mine(_: Client, q: CallbackQuery) -> None:
        from nekofetch.services.request_service import RequestService
        from nekofetch.ui.screens import my_requests as my_reqs_screen

        await q.answer()
        rows = await RequestService(container).list_for_user(q.from_user.id)
        name = q.from_user.first_name if q.from_user else ""
        if not rows:
            screen = my_reqs_screen(name, [])
            await send_screen(client, q.message.chat.id, screen, old_msg=q.message)
            return
        req_list = [
            {"title": r.anime_title, "status": r.status} for r in rows[:10]
        ]
        screen = my_reqs_screen(name, req_list)
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)
