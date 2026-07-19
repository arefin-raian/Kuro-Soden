"""Senku's channel-creation wizard — Phase 2 of the distribution flow.

An FSM-backed, button-driven flow keyed by **request code**. It replaces the old
``/create`` / ``/generate`` text stubs with a real stepper:

    open → franchise map → Begin → title → username → poster → description
         → add-admins → "I've created it" → send @username → verify → thumbnails

Every step is one voiced card with recurring artwork and clean buttons (the
cross-bot bar set by Lelouch/Levi). All copy comes from :mod:`senku_voice`; the
channel essentials (title / username / description) come from
:mod:`channel_essentials`, which reuses NekoFetch's exact auto-pipeline logic so
the manual output matches what the automated build would have produced. The
working set (franchise + entries + chosen channel) lives in
:class:`DistributionCache`, keyed by code.

Routing sits under a single ``^senku\\|wiz\\|`` dispatcher registered in group 0,
ahead of the ``^senku\\|`` home/settings fallback in ``app.py``. The thumbnail
loop (Phase 3) is entered via ``_enter_thumbnails`` — a stub here that hands off
to the Phase 3 handler once it lands.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import Role
from nekofetch.ui.artwork import (
    ensure_anime_art, key_for_franchise, next_anime_art, pick_artwork,
)
from nekofetch.ui.components import cb
from nekofetch.ui.screens import Screen, card, send_screen

from kurosoden.shared import senku_voice as V
from kurosoden.shared.channel_essentials import build_channel_essentials
from kurosoden.shared.distribution_cache import DistributionCache
from kurosoden.shared import franchise_map
from kurosoden.shared.senku_thumbnail_adapter import SenkuThumbnailAdapter

log = get_logger(__name__)

BOT = "senku"

# FSM state: waiting for the admin to send the created channel's @username / id.
STATE_AWAIT_CHANNEL = "senku:wiz:await_channel"

# FSM state: waiting for the admin to paste a corrected watch order (Phase 4 edit).
STATE_AWAIT_ORDER = "senku:wiz:await_order"

# FSM state: waiting for the admin to send their own asset image (logo/poster/bg).
STATE_AWAIT_UPLOAD = "senku:wiz:await_upload"

# Commands that must never be swallowed by the free-text channel step.
_RESERVED = ["start", "tasks", "create", "generate", "settings", "help", "cancel"]


def register(client: Client, container: Container) -> None:
    fsm = FSM(container.redis, bot="senku")
    cache = DistributionCache(container)
    thumbs = SenkuThumbnailAdapter(container)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _staff(obj) -> bool:
        user = getattr(obj, "nf_user", None)
        if user is None:
            return False
        try:
            return Role(user.role) in (Role.STAFF, Role.ADMIN)
        except Exception:  # noqa: BLE001 — unknown role string ⇒ not staff
            return False

    async def _art(franchise: dict | None, title: str):
        """This franchise's rotating backdrop, or Senku's character art.

        Mirrors the Lelouch/Levi rule (``requests.py``): a card about a specific
        title carries that title's art; otherwise it falls back to Senku's gallery
        — never bare. Returns a ``Path`` or URL string; ``card`` accepts both.
        """
        if franchise:
            try:
                key = key_for_franchise(franchise, title=title)
                await ensure_anime_art(key, tmdb=container.tmdb, title=title,
                                       franchise=franchise)
                return next_anime_art(key, fallback_bot=BOT)
            except Exception as exc:  # noqa: BLE001 — art is decorative
                log.debug("senku.wiz.art_failed", title=title, error=str(exc))
        return pick_artwork(BOT)

    async def _title_of(code: str, franchise: dict | None) -> str:
        if franchise:
            return (franchise.get("english") or franchise.get("title")
                    or franchise.get("anime_title") or code)
        return code

    async def _open(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Seed the cache and render the franchise map + Begin."""
        franchise = await cache.ensure(code)
        if not franchise:
            await send_screen(
                client, chat_id,
                card(V.NO_TASK, image=pick_artwork(BOT), bot_name=BOT,
                     buttons=[[(V.BTN_HOME, cb(BOT, "home"))]]),
                old_msg=old_msg,
            )
            return
        title = await _title_of(code, franchise)
        entries = await cache.get_entries(code)
        tree = franchise_map.render_tree(entries, title)
        screen = card(
            f"{V.handoff_card(title, code, len(entries))}\n\n{tree}",
            image=await _art(franchise, title), bot_name=BOT,
            buttons=[
                [(V.BTN_BEGIN, cb(BOT, "wiz", "chan", code))],
                [(V.BTN_HOME, cb(BOT, "home"))],
            ],
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    async def _channel_ctx(code: str):
        """Resolve (franchise, title, essentials) for a channel step, or None.

        Shared by every channel sub-step so the essentials (title / username /
        description / poster link) are computed the same way each card.
        """
        franchise = await cache.get_franchise(code) or await cache.ensure(code)
        if not franchise:
            return None
        title = await _title_of(code, franchise)
        ess = await build_channel_essentials(
            container,
            anime_doc_id=franchise.get("anime_doc_id"),
            franchise=franchise,
        )
        return franchise, title, ess

    async def _no_task(chat_id: int, *, old_msg: Message | None) -> None:
        await send_screen(
            client, chat_id,
            card(V.NO_TASK, image=pick_artwork(BOT), bot_name=BOT,
                 buttons=[[(V.BTN_HOME, cb(BOT, "home"))]]),
            old_msg=old_msg,
        )

    async def _channel_step(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Channel-creation step 1 — title + suggested username (both tap-to-copy).

        The channel essentials overflow a single 1000-char caption, so the flow is
        a three-card stepper (title/username → poster/description → admins) with no
        silent truncation: 1) title & username, 2) poster & description, 3) admins.
        """
        ctx = await _channel_ctx(code)
        if ctx is None:
            await _no_task(chat_id, old_msg=old_msg)
            return
        franchise, title, ess = ctx
        body = "\n\n".join([
            V.channel_intro(title),
            V.channel_title_block(ess.title),
            V.channel_username_block(ess.username),
        ])
        screen = card(
            body, image=await _art(franchise, title), bot_name=BOT,
            buttons=[
                [(V.BTN_CONTINUE, cb(BOT, "wiz", "chan2", code))],
                [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))],
            ],
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    async def _channel_step2(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Channel-creation step 2 — profile picture (TMDB link) + description."""
        ctx = await _channel_ctx(code)
        if ctx is None:
            await _no_task(chat_id, old_msg=old_msg)
            return
        franchise, title, ess = ctx
        body = "\n\n".join([
            V.channel_pfp_line(),
            V.channel_description_block(ess.description),
        ])
        screen = card(
            body, image=await _art(franchise, title), bot_name=BOT,
            url_buttons=[[(V.BTN_TMDB_POSTER, ess.poster_search_url)]],
            buttons=[
                [(V.BTN_CONTINUE, cb(BOT, "wiz", "chan3", code))],
                [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))],
            ],
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    async def _channel_step3(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Channel-creation step 3 — add Senku + Gojo as admins, then confirm done."""
        ctx = await _channel_ctx(code)
        if ctx is None:
            await _no_task(chat_id, old_msg=old_msg)
            return
        franchise, title, _ess = ctx
        screen = card(
            V.CHANNEL_ADMINS_LINE, image=await _art(franchise, title), bot_name=BOT,
            buttons=[
                [(V.BTN_CHANNEL_DONE, cb(BOT, "wiz", "chandone", code))],
                [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))],
            ],
        )
        await send_screen(client, chat_id, screen, old_msg=old_msg)

    async def _ask_channel(chat_id: int, user_id: int, code: str,
                           *, old_msg: Message | None) -> None:
        await fsm.set(user_id, STATE_AWAIT_CHANNEL, code=code)
        await send_screen(
            client, chat_id,
            card(V.CHANNEL_ASK_USERNAME, image=pick_artwork(BOT), bot_name=BOT,
                 buttons=[[(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
            old_msg=old_msg,
        )

    async def _verify_and_store(chat_id: int, user_id: int, code: str, raw: str) -> None:
        """Resolve the channel, confirm Senku is an admin there, store it, advance."""
        handle = raw.strip()
        target: str | int = handle
        if not handle.startswith("@") and not handle.lstrip("-").isdigit():
            target = f"@{handle}"
        elif handle.lstrip("-").isdigit():
            target = int(handle)

        chat = None
        is_admin = False
        try:
            chat = await client.get_chat(target)
            me = await client.get_chat_member(chat.id, "me")
            status = getattr(getattr(me, "status", None), "value", str(getattr(me, "status", "")))
            is_admin = status in ("administrator", "creator")
        except Exception as exc:  # noqa: BLE001 — bad handle / not a member / not admin
            log.info("senku.wiz.verify_failed", code=code, handle=handle, error=str(exc))

        display = f"@{chat.username}" if chat and chat.username else (
            chat.title if chat else handle
        )
        if chat is None or not is_admin:
            await send_screen(
                client, chat_id,
                card(V.channel_verify_failed(display), image=pick_artwork(BOT), bot_name=BOT,
                     buttons=[
                         [(V.BTN_CHANNEL_DONE, cb(BOT, "wiz", "chandone", code))],
                         [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))],
                     ]),
            )
            return

        await fsm.clear(user_id)
        await cache.set_channel(code, handle=display, chat_id=chat.id)
        await send_screen(
            client, chat_id,
            card(V.channel_verified(display), image=pick_artwork(BOT), bot_name=BOT,
                 buttons=[[(V.BTN_CONTINUE, cb(BOT, "wiz", "thumbs", code))]]),
        )

    async def _enter_thumbnails(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Enter the per-entry thumbnail loop (Phase 3): intro → first pending entry."""
        entries = await cache.get_entries(code)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        await send_screen(
            client, chat_id,
            card(V.thumb_intro(title, len(entries)), image=await _art(franchise, title),
                 bot_name=BOT,
                 buttons=[[(V.BTN_CONTINUE, cb(BOT, "wiz", "tnext", code))],
                          [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
            old_msg=old_msg,
        )

    async def _thumb_next(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Advance the loop: render the next asset card, or finish → watch order."""
        entry = await thumbs.next_pending(code)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        if entry is None:
            # Every entry rendered — hand to Phase 4 (watch-order confirm).
            total = len(await cache.get_entries(code))
            await send_screen(
                client, chat_id,
                card(V.thumb_generated(total, total), image=await _art(franchise, title),
                     bot_name=BOT,
                     buttons=[[(V.BTN_ORDER_CORRECT, cb(BOT, "wiz", "order", code))],
                              [(V.BTN_HOME, cb(BOT, "home"))]]),
                old_msg=old_msg,
            )
            return
        sel = await cache.get_selection(code, entry.index)
        asset = thumbs.next_asset(sel)
        if asset is None:
            # All assets picked but not yet rendered — offer Generate.
            await _thumb_generate_card(chat_id, code, entry, old_msg=old_msg)
            return
        await _thumb_asset_card(chat_id, code, entry, asset, old_msg=old_msg)

    async def _thumb_asset_card(chat_id: int, code: str, entry, asset: str,
                                *, old_msg: Message | None) -> None:
        """One asset-pick card: header + gallery link + numbered buttons."""
        entries = await cache.get_entries(code)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        assets, gallery, rows = await thumbs.asset_step(code, entry, asset)
        # Manual override: the admin can upload their own image instead of picking
        # a numbered TMDB asset (senku|wiz|upl|<code>|<index>|<asset>).
        upload_row = [(V.BTN_UPLOAD_OWN,
                       cb(BOT, "wiz", "upl", code, str(entry.index), asset))]
        if not assets:
            # TMDB had nothing for this type — still let the admin upload their own
            # rather than dead-ending. The loop runs in the admin's private DM, so
            # chat_id IS their telegram user id (what the FSM keys on).
            await _ask_upload(chat_id, chat_id, code, entry.index, asset,
                              old_msg=old_msg)
            return
        body = "\n\n".join([
            V.thumb_entry_header(entry.label, entry.index, len(entries)),
            V.thumb_pick_prompt(asset),
        ])
        url_buttons = [[(V.BTN_SHOW_LOGOS if asset == "logo" else
                         V.BTN_SHOW_POSTERS if asset == "poster" else
                         V.BTN_SHOW_BACKDROPS, gallery)]] if gallery else None
        await send_screen(
            client, chat_id,
            card(body, image=await _art(franchise, title), bot_name=BOT,
                 url_buttons=url_buttons,
                 buttons=rows + [upload_row,
                                 [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
            old_msg=old_msg,
        )

    async def _ask_upload(chat_id: int, user_id: int, code: str, index: int,
                          asset: str, *, old_msg: Message | None) -> None:
        """Arm the manual-upload step: prompt the admin to send their own image."""
        await fsm.set(user_id, STATE_AWAIT_UPLOAD, code=code, index=index, asset=asset)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        await send_screen(
            client, chat_id,
            card(V.thumb_upload_prompt(asset), image=await _art(franchise, title),
                 bot_name=BOT,
                 buttons=[[(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
            old_msg=old_msg,
        )

    async def _thumb_generate_card(chat_id: int, code: str, entry,
                                   *, old_msg: Message | None) -> None:
        """All three assets picked — offer the Generate button for this entry."""
        entries = await cache.get_entries(code)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        await send_screen(
            client, chat_id,
            card(V.thumb_entry_header(entry.label, entry.index, len(entries)),
                 image=await _art(franchise, title), bot_name=BOT,
                 buttons=[[(V.BTN_GENERATE, cb(BOT, "wiz", "gen", code, str(entry.index)))],
                          [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
            old_msg=old_msg,
        )

    async def _thumb_pick(q: CallbackQuery, code: str, index: int, asset: str,
                          number: int) -> None:
        """Store a numbered pick, then advance to the next asset or Generate."""
        sel, nxt = await thumbs.store_pick(code, index, asset, number)
        await q.answer(V.thumb_selected(asset, number))
        await _thumb_next(q.message.chat.id, code, old_msg=q.message)

    async def _thumb_generate(q: CallbackQuery, code: str, index: int) -> None:
        """Render one entry's thumbnail, upload it for reference, then advance."""
        entry = await cache.get_entry(code, index)
        if entry is None:
            await q.answer("Entry not found.", show_alert=True)
            return
        await q.answer("Rendering…")
        path = await thumbs.render_entry(code, entry)
        if path is None:
            await send_screen(
                client, q.message.chat.id,
                card(V.THUMB_GALLERY_FAIL, image=pick_artwork(BOT), bot_name=BOT,
                     buttons=[[(V.BTN_GENERATE, cb(BOT, "wiz", "gen", code, str(index)))],
                              [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
                old_msg=q.message,
            )
            return
        # Upload the rendered card so the admin sees the result inline.
        try:
            await client.send_photo(q.message.chat.id, str(path))
        except Exception as exc:  # noqa: BLE001 — preview is best-effort
            log.debug("senku.wiz.thumb_preview_failed", code=code, error=str(exc))
        await _thumb_next(q.message.chat.id, code, old_msg=None)

    async def _enter_watch_order(chat_id: int, code: str, *, old_msg: Message | None) -> None:
        """Enter the watch-order confirm step (Phase 4) — the last gate before publish.

        Renders the numbered order with Confirm/Edit buttons. Confirm publishes;
        Edit drops into a free-text step (``STATE_AWAIT_ORDER``) that re-maps the
        pasted order and returns here for a second look.
        """
        entries = await cache.get_entries(code)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        order_html = franchise_map.render_watch_order(entries)
        await send_screen(
            client, chat_id,
            card(V.watch_order_card(title, order_html),
                 image=await _art(franchise, title), bot_name=BOT,
                 buttons=[
                     [(V.BTN_ORDER_CORRECT, cb(BOT, "wiz", "post", code))],
                     [(V.BTN_ORDER_EDIT, cb(BOT, "wiz", "oedit", code))],
                     [(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))],
                 ]),
            old_msg=old_msg,
        )

    async def _ask_order_edit(chat_id: int, user_id: int, code: str,
                              *, old_msg: Message | None) -> None:
        """Prompt for a corrected watch order and arm the free-text step."""
        await fsm.set(user_id, STATE_AWAIT_ORDER, code=code)
        entries = await cache.get_entries(code)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        copy_block = franchise_map.render_copy_block(entries)
        body = f"{V.WATCH_ORDER_EDIT_PROMPT}\n\n<pre>{copy_block}</pre>"
        await send_screen(
            client, chat_id,
            card(body, image=await _art(franchise, title), bot_name=BOT,
                 buttons=[[(V.BTN_CANCEL, cb(BOT, "wiz", "cancel", code))]]),
            old_msg=old_msg,
        )

    async def _publish(chat_id: int, user_id: int, code: str,
                       *, old_msg: Message | None) -> None:
        """Post the content pack into the channel, then hand off to Gojo."""
        await fsm.clear(user_id)
        franchise = await cache.get_franchise(code)
        title = await _title_of(code, franchise)
        # "Working" card — publishing walks the whole pack + catbox uploads.
        await send_screen(
            client, chat_id,
            card(V.publishing(title), image=await _art(franchise, title), bot_name=BOT),
            old_msg=old_msg,
        )
        try:
            from kurosoden.shared.senku_publisher import SenkuPublisher

            await SenkuPublisher(container).publish(client, code)
        except Exception as exc:  # noqa: BLE001 — surface a clean failure card
            log.warning("senku.wiz.publish_failed", code=code, error=str(exc))
            await send_screen(
                client, chat_id,
                card(V.PUBLISH_FAIL, image=pick_artwork(BOT), bot_name=BOT,
                     buttons=[[(V.BTN_PUBLISH, cb(BOT, "wiz", "post", code))],
                              [(V.BTN_HOME, cb(BOT, "home"))]]),
                old_msg=None,
            )
            return
        # Hand the request to Gojo (publish stage) and clear the working cache.
        try:
            from kurosoden.shared.handoff import handoff_distribution_to_publish

            await handoff_distribution_to_publish(container, code, title)
        except Exception as exc:  # noqa: BLE001 — handoff is best-effort
            log.warning("senku.wiz.handoff_failed", code=code, error=str(exc))
        await cache.clear(code)
        await send_screen(
            client, chat_id,
            card(V.published_done(title), image=await _art(franchise, title), bot_name=BOT,
                 buttons=[[(V.BTN_TASKS, cb(BOT, "tasks"))],
                          [(V.BTN_HOME, cb(BOT, "home"))]]),
            old_msg=None,
        )

    # ── /create — open the wizard for the admin's most recent task ─────────────
    @client.on_message(filters.command("create") & filters.private)
    async def _create_cmd(_: Client, message: Message) -> None:
        if not _staff(message):
            return
        parts = (message.text or "").split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else await _latest_task(container, message)
        if not code:
            await message.reply(V.TASKS_EMPTY)
            return
        await _open(message.chat.id, code, old_msg=None)

    # ── Handoff / task entry: senku|wiz|open|<code> ────────────────────────────
    @client.on_callback_query(filters.regex(r"^senku\|wiz\|"), group=0)
    async def _wiz_router(_: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        if not _staff(q):
            await q.answer("Not for you.", show_alert=True)
            return
        parts = q.data.split("|")
        action = parts[2] if len(parts) > 2 else ""
        code = parts[3] if len(parts) > 3 else ""
        chat_id = q.message.chat.id

        if action == "open":
            await q.answer()
            await _open(chat_id, code, old_msg=q.message)
        elif action == "chan":
            await q.answer()
            await _channel_step(chat_id, code, old_msg=q.message)
        elif action == "chan2":
            await q.answer()
            await _channel_step2(chat_id, code, old_msg=q.message)
        elif action == "chan3":
            await q.answer()
            await _channel_step3(chat_id, code, old_msg=q.message)
        elif action == "chandone":
            await q.answer()
            await _ask_channel(chat_id, q.from_user.id, code, old_msg=q.message)
        elif action == "thumbs":
            await q.answer()
            await _enter_thumbnails(chat_id, code, old_msg=q.message)
        elif action == "tnext":
            await q.answer()
            await _thumb_next(chat_id, code, old_msg=q.message)
        elif action == "pick":
            # senku|wiz|pick|<code>|<index>|<asset>|<number>
            try:
                index, asset, number = int(parts[4]), parts[5], int(parts[6])
            except (IndexError, ValueError):
                await q.answer("Bad selection.", show_alert=True)
                return
            await _thumb_pick(q, code, index, asset, number)
        elif action == "upl":
            # senku|wiz|upl|<code>|<index>|<asset> — arm the manual-upload step.
            try:
                index, asset = int(parts[4]), parts[5]
            except (IndexError, ValueError):
                await q.answer("Bad asset.", show_alert=True)
                return
            await _ask_upload(chat_id, q.from_user.id, code, index, asset,
                              old_msg=q.message)
            await q.answer()
        elif action == "gen":
            # senku|wiz|gen|<code>|<index>
            try:
                index = int(parts[4])
            except (IndexError, ValueError):
                await q.answer("Bad entry.", show_alert=True)
                return
            await _thumb_generate(q, code, index)
        elif action == "order":
            # Watch-order confirm card (Phase 4).
            await q.answer()
            await _enter_watch_order(chat_id, code, old_msg=q.message)
        elif action == "oedit":
            # "Edit order" — arm the free-text re-map step.
            await q.answer()
            await _ask_order_edit(chat_id, q.from_user.id, code, old_msg=q.message)
        elif action == "post":
            # "Order is correct" — publish the pack into the channel.
            await q.answer()
            await _publish(chat_id, q.from_user.id, code, old_msg=q.message)
        elif action == "cancel":
            await fsm.clear(q.from_user.id)
            await q.answer("Cancelled.")
            await send_screen(
                client, chat_id,
                card(V.HOME_BODY, image=pick_artwork(BOT), bot_name=BOT,
                     buttons=[[(V.BTN_TASKS, cb(BOT, "tasks"))],
                              [(V.BTN_HOME, cb(BOT, "home"))]]),
                old_msg=q.message,
            )
        else:
            await q.answer("Unknown step.", show_alert=True)

    # ── Free-text channel step (group=2, only while awaiting the channel) ──────
    @client.on_message(
        filters.text & filters.private & ~filters.command(_RESERVED),
        group=2,
    )
    async def _channel_text(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, data = await fsm.get(message.from_user.id)
        if state not in (STATE_AWAIT_CHANNEL, STATE_AWAIT_ORDER):
            return  # not our turn
        if not _staff(message):
            return
        code = data.get("code", "")
        raw = (message.text or "").strip()

        if state == STATE_AWAIT_ORDER:
            if not raw:
                await message.reply(V.watch_order_edit_failed())
                return
            entries = await cache.apply_order_correction(code, raw)
            if not entries:
                await message.reply(V.watch_order_edit_failed())
                return
            await fsm.clear(message.from_user.id)
            # Re-render the confirm card with the corrected order for a second look.
            await _enter_watch_order(message.chat.id, code, old_msg=None)
            return

        if not raw:
            await message.reply(V.channel_missing("the channel @username or ID"))
            return
        await _verify_and_store(message.chat.id, message.from_user.id, code, raw)

    # ── Manual asset upload (group=2, only while awaiting an uploaded image) ────
    @client.on_message(
        (filters.photo | filters.document) & filters.private,
        group=2,
    )
    async def _upload_media(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, data = await fsm.get(message.from_user.id)
        if state != STATE_AWAIT_UPLOAD:
            return  # not our turn
        if not _staff(message):
            return
        code = data.get("code", "")
        index = int(data.get("index", 0))
        asset = data.get("asset", "")

        # A document must actually be an image — reject PDFs, archives, etc.
        if message.document and not (message.document.mime_type or "").startswith("image/"):
            await message.reply(V.THUMB_UPLOAD_BAD)
            return

        try:
            buf = await client.download_media(message, in_memory=True)
            file_bytes = buf.getvalue()
        except Exception as exc:  # noqa: BLE001
            log.warning("senku.wiz.upload_download_failed", code=code, error=str(exc))
            await message.reply(V.THUMB_UPLOAD_FAILED)
            return

        try:
            await thumbs.store_upload(code, index, asset, file_bytes)
        except Exception as exc:  # noqa: BLE001 — catbox host hiccup
            log.warning("senku.wiz.upload_store_failed", code=code, error=str(exc))
            await message.reply(V.THUMB_UPLOAD_FAILED)
            return

        await fsm.clear(message.from_user.id)
        await message.reply(V.thumb_uploaded(asset))
        # Advance to the next asset (or the Generate card) just like a numbered pick.
        await _thumb_next(message.chat.id, code, old_msg=None)


async def _latest_task(container: Container, message: Message) -> str | None:
    """The admin's newest active distribution task code, if any."""
    try:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        engine = AdminAssignmentEngine(container.pg_sessionmaker)
        active = await engine.get_active_tasks(message.from_user.id)
        return active[0].request_code if active else None
    except Exception as exc:  # noqa: BLE001
        log.warning("senku.wiz.latest_task_failed", error=str(exc))
        return None
