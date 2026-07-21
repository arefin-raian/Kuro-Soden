"""Lelouch admin self-service profile — the ``pr|`` callback surface.

A non-owner admin's home shows **My Profile** instead of Command. This module
owns that surface: a read card plus guided editors for country, timezone, daily
-hours cap, and weekday/weekend time slots. The owner's admin-management flow
(``mg|``) also reuses the same :class:`ManagementService` setters when mustering
a rank, so an admin can be seeded with a profile and later edit it here.

Callback grammar (all ``pr|``):
  home                       → the profile card
  country / hours            → start a text capture for that field
  slots|<weekday|weekend>    → start a slots text capture
  tz                         → hand off to the shared timezone picker (lelouch|tz|home)
  board                      → the read-only Board (stats), back to profile

Timezone editing reuses :func:`register_timezone_ui` (already wired on Lelouch),
so this module only needs the button that jumps to it.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import Role
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import Screen, send_screen

from kurosoden.shared import admin_profile as P
from kurosoden.shared import lelouch_voice as V
from kurosoden.shared.management_service import ManagementService

log = get_logger(__name__)

BOT = "lelouch"
_STATE = "lelouch_profile:edit"  # fsm state; data carries {"field": ...}


def _svc(container: Container) -> ManagementService:
    return ManagementService(container.pg_sessionmaker)


def _is_admin(obj) -> bool:
    user = getattr(obj, "nf_user", None)
    if user is None:
        return False
    try:
        return Role(user.role) in (Role.STAFF, Role.ADMIN)
    except Exception:  # noqa: BLE001
        return False


def _profile_screen(v) -> Screen:
    weekday = P.format_slots(v.slots_weekday) if v else "—"
    weekend = P.format_slots(v.slots_weekend) if v else "—"
    caption = V.profile_card(v, weekday_str=weekday, weekend_str=weekend)
    rows = [
        [(V.BTN_EDIT_COUNTRY, cb(BOT, "pr", "country")),
         (V.BTN_EDIT_TIMEZONE, cb(BOT, "tz", "home"))],
        [(V.BTN_EDIT_HOURS, cb(BOT, "pr", "hours"))],
        [(V.BTN_EDIT_WEEKDAY, cb(BOT, "pr", "slots", "weekday")),
         (V.BTN_EDIT_WEEKEND, cb(BOT, "pr", "slots", "weekend"))],
        [(V.BTN_VIEW_BOARD, cb(BOT, "queue", 0))],
        [(V.BTN_HOME, cb(BOT, "home"))],
    ]
    return Screen(caption=caption, image=pick_artwork(BOT), keyboard=keyboard(*rows))


async def render_profile(client: Client, container: Container, chat_id: int,
                         admin_id: int, old_msg: Message | None) -> None:
    svc = _svc(container)
    # Ensure a row exists so a freshly-added admin can edit immediately.
    v = await svc.get_admin(admin_id)
    if v is None:
        await svc.ensure_admin(admin_id)
        v = await svc.get_admin(admin_id)
    await send_screen(client, chat_id, _profile_screen(v), old_msg=old_msg)


def register(client: Client, container: Container, *, input_group: int = 7) -> None:
    """Wire the ``pr|`` profile surface. ``input_group`` must be distinct from the
    settings engine (5) and timezone picker (6) capture groups."""
    fsm = FSM(container.redis, bot="lelouch-profile")

    async def _guard(q: CallbackQuery) -> bool:
        if q.message is None:
            await q.answer()
            return False
        if not _is_admin(q):
            await q.answer("🔒 Admins only.", show_alert=True)
            return False
        return True

    @client.on_callback_query(filters.regex(r"^lelouch\|pr\|home$"))
    async def _home(_: Client, q: CallbackQuery) -> None:
        if not await _guard(q):
            return
        await q.answer()
        await render_profile(client, container, q.message.chat.id,
                             q.from_user.id, q.message)

    @client.on_callback_query(filters.regex(r"^lelouch\|pr\|country$"))
    async def _country(_: Client, q: CallbackQuery) -> None:
        if not await _guard(q):
            return
        await fsm.set(q.from_user.id, _STATE, field="country")
        await q.answer()
        await q.message.reply(V.PROFILE_ASK_COUNTRY, parse_mode=ParseMode.HTML)

    @client.on_callback_query(filters.regex(r"^lelouch\|pr\|hours$"))
    async def _hours(_: Client, q: CallbackQuery) -> None:
        if not await _guard(q):
            return
        await fsm.set(q.from_user.id, _STATE, field="hours")
        await q.answer()
        await q.message.reply(V.PROFILE_ASK_HOURS, parse_mode=ParseMode.HTML)

    @client.on_callback_query(filters.regex(r"^lelouch\|pr\|slots\|"))
    async def _slots(_: Client, q: CallbackQuery) -> None:
        if not await _guard(q):
            return
        kind = q.data.split("|", 3)[3]
        kind = "weekend" if kind == "weekend" else "weekday"
        await fsm.set(q.from_user.id, _STATE, field=f"slots:{kind}")
        await q.answer()
        await q.message.reply(V.profile_ask_slots(kind), parse_mode=ParseMode.HTML)

    @client.on_message(
        filters.text & filters.private & ~filters.command(["start", "cancel"]),
        group=input_group,
    )
    async def _capture(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, data = await fsm.get(message.from_user.id)
        if state != _STATE:
            return
        if not _is_admin(message):
            return
        field = data.get("field", "")
        raw = (message.text or "").strip()
        svc = _svc(container)
        admin_id = message.from_user.id

        if field == "country":
            await svc.set_country(admin_id, raw)
        elif field == "hours":
            try:
                await svc.set_max_hours(admin_id, int(raw))
            except (ValueError, TypeError):
                await message.reply(
                    "Send a whole number of hours, like <code>3</code>.",
                    parse_mode=ParseMode.HTML,
                )
                return
        elif field.startswith("slots:"):
            kind = field.split(":", 1)[1]
            if raw.lower() in ("none", "clear", "-"):
                slots: list = []
            else:
                slots = P.parse_slots(raw)
                if not slots:
                    await message.reply(
                        "I couldn't read any slots there. Use lines like "
                        "<code>6:00 PM - 8:00 PM</code>, or send "
                        "<code>none</code> to clear.",
                        parse_mode=ParseMode.HTML,
                    )
                    return
            await svc.set_slots(admin_id, kind, slots)
        else:
            await fsm.clear(admin_id)
            return

        await fsm.clear(admin_id)
        # Re-render the profile card so the admin sees the saved change.
        await render_profile(client, container, message.chat.id, admin_id, None)

    @client.on_message(filters.command("cancel") & filters.private, group=input_group)
    async def _cancel(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, _data = await fsm.get(message.from_user.id)
        if state == _STATE:
            await fsm.clear(message.from_user.id)
            await message.reply("Okay, left your profile unchanged.",
                                parse_mode=ParseMode.HTML)
