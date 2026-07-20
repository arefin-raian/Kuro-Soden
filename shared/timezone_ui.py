"""Per-admin timezone picker — a small, reusable settings surface.

Timezone is a property of the *person*, not the bot's config: it lives on
``AdminAvailability.timezone`` and only changes how that admin enters and reads
scheduled-post times (storage stays UTC; shift windows stay UTC). Because it's
per-admin it can't ride the config-backed :class:`SettingsService`, so this
module wires its own tiny hub → pick → save flow under a ``{bot}|tz|…`` callback
namespace. Any bot can call :func:`register_timezone_ui` to gain a
"🌍 My Timezone" screen.

Common zones are one-tap buttons; anything else can be typed as a raw IANA name
(e.g. ``America/Chicago``), validated against ``zoneinfo`` before saving.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

from nekofetch.bots.fsm import FSM
from nekofetch.core.container import Container
from nekofetch.core.timefmt import tz_offset_label
from nekofetch.ui.artwork import pick_artwork
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import Screen, send_screen

# A short, sensible menu for this project's audience + the admins' likely zones.
# (value, friendly label) — value is a real IANA name that zoneinfo accepts.
COMMON_ZONES: list[tuple[str, str]] = [
    ("Asia/Dhaka", "🇧🇩 Dhaka"),
    ("Asia/Kolkata", "🇮🇳 Kolkata"),
    ("Asia/Karachi", "🇵🇰 Karachi"),
    ("Asia/Dubai", "🇦🇪 Dubai"),
    ("Asia/Tokyo", "🇯🇵 Tokyo"),
    ("Asia/Singapore", "🇸🇬 Singapore"),
    ("Europe/London", "🇬🇧 London"),
    ("Europe/Berlin", "🇩🇪 Berlin"),
    ("America/New_York", "🇺🇸 New York"),
    ("America/Los_Angeles", "🇺🇸 Los Angeles"),
    ("UTC", "🌐 UTC"),
]


def _valid_zone(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
        return True
    except Exception:  # noqa: BLE001 — unknown name / missing tzdata
        return False


def _tz_screen(bot: str, current: str | None) -> Screen:
    cur = current or "Asia/Dhaka (default)"
    label = tz_offset_label(current)
    rows: list[list[tuple[str, str]]] = []
    pairs = [(lbl, cb(bot, "tz", "set", val)) for val, lbl in COMMON_ZONES]
    for i in range(0, len(pairs), 2):
        rows.append(pairs[i : i + 2])
    rows.append([("⌨️ Type an IANA name", cb(bot, "tz", "type"))])
    rows.append([("⇐ Back", cb(bot, "settings"))])
    caption = (
        "🌍 <b>My Timezone</b>\n\n"
        f"Right now you're on <b>{cur}</b> (<b>{label}</b>).\n\n"
        "This is just for <i>you</i> — it sets how you type and read schedule "
        "times. Everyone else keeps their own. Storage and shift hours are "
        "untouched.\n\n"
        "<i>Tap a city, or type any IANA name like "
        "<code>America/Chicago</code>.</i>"
    )
    return Screen(caption=caption, image=pick_artwork(bot), keyboard=keyboard(*rows))


def register_timezone_ui(
    client: Client, container: Container, bot: str, *,
    group: int = 0, input_group: int = 6,
) -> None:
    """Wire the ``{bot}|tz|…`` timezone picker + free-text IANA capture.

    ``input_group`` must differ from every other text-capture handler on the same
    client: Pyrogram runs only the first matching handler per group, so a shared
    group would let one capture swallow the other's messages. The settings engine
    uses group 5, so this defaults to 6.
    """
    fsm = FSM(container.redis, bot=f"{bot}-tz")
    state_type = f"{bot}:await_timezone"

    async def _current(admin_id: int) -> str | None:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        return await AdminAssignmentEngine(container.pg_sessionmaker).get_timezone(admin_id)

    async def _save(admin_id: int, name: str, admin_name: str | None) -> None:
        from kurosoden.shared.admin_assignment import AdminAssignmentEngine

        await AdminAssignmentEngine(container.pg_sessionmaker).set_timezone(
            admin_id, name, admin_name=admin_name,
        )

    @client.on_callback_query(filters.regex(rf"^{bot}\|tz\|home$"), group=group)
    async def _tz_home(_: Client, q: CallbackQuery) -> None:
        await q.answer()
        current = await _current(q.from_user.id)
        await send_screen(client, q.message.chat.id, _tz_screen(bot, current),
                          old_msg=q.message)

    @client.on_callback_query(filters.regex(rf"^{bot}\|tz\|set\|"), group=group)
    async def _tz_set(_: Client, q: CallbackQuery) -> None:
        name = q.data.split("|", 3)[3]
        if not _valid_zone(name):
            await q.answer("That timezone isn't recognised.", show_alert=True)
            return
        await _save(q.from_user.id, name, q.from_user.first_name)
        await q.answer(f"Timezone set to {name} ({tz_offset_label(name)})")
        await send_screen(client, q.message.chat.id, _tz_screen(bot, name),
                          old_msg=q.message)

    @client.on_callback_query(filters.regex(rf"^{bot}\|tz\|type$"), group=group)
    async def _tz_type(_: Client, q: CallbackQuery) -> None:
        await fsm.set(q.from_user.id, state_type)
        await q.answer()
        await q.message.reply(
            "🌍 Send an IANA timezone name — like <code>America/Chicago</code>, "
            "<code>Europe/Paris</code>, or <code>Asia/Manila</code>.\n\n"
            "<code>/cancel</code> to keep what you have.",
            parse_mode=ParseMode.HTML,
        )

    @client.on_message(
        filters.text & filters.private & ~filters.command(["start", "cancel"]),
        group=input_group,
    )
    async def _tz_capture(_: Client, message: Message) -> None:
        if not message.from_user:
            return
        state, _data = await fsm.get(message.from_user.id)
        if state != state_type:
            return
        name = (message.text or "").strip()
        if not _valid_zone(name):
            await message.reply(
                f"🌍 I don't recognise <code>{name}</code>. Use an IANA name like "
                "<code>America/Chicago</code>. <code>/cancel</code> to stop.",
                parse_mode=ParseMode.HTML,
            )
            return
        await fsm.clear(message.from_user.id)
        await _save(message.from_user.id, name, message.from_user.first_name)
        await message.reply(
            f"🌍 <b>Timezone set to {name}</b> ({tz_offset_label(name)}). "
            "Schedule times now read in your local clock.",
            parse_mode=ParseMode.HTML,
        )
