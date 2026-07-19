"""Admin panel + Settings control center.

The admin **home** (queue / analytics / staff / approvals, plus the owner-only
infrastructure buttons) lives here. The **Settings** surface itself is delegated
to :func:`kurosoden.shared.settings_ui.register_settings` — the same human-friendly
engine the four pipeline bots use — so there is no 2× drift and no raw presentation
(bare slugs, ``{tokens}``, ``/command`` hints). The engine introspects the live
``AppConfig`` through :class:`SettingsService`: booleans get a toggle, enums a
tap-to-pick picker, channel/sticker ids a guided capture, templates a live preview.
Owner-only infrastructure sections stay gated exactly as before — hidden from the
hub for non-owners and denied on tap.

``/resetoverrides`` (clear-overrides) stays in ``commands.py``.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from nekofetch.core.container import Container
from nekofetch.domain.enums import Permission
from nekofetch.localization.messages import M, t
from nekofetch.services.auth_service import AuthService
from nekofetch.ui.components import cb, keyboard
from nekofetch.ui.screens import Screen, send_screen

# Order in which config sections appear in the Settings hub. Every entry must map
# to a real ``AppConfig`` attribute (the shared engine drops missing ones) and has
# a friendly label in ``kurosoden.shared.settings_ui.SECTION_LABELS``.
_SETTINGS_ORDER = (
    "features", "sources", "downloads", "acquisition", "processing",
    "rename", "metadata", "thumbnail", "watermark", "branding",
    "distribution", "queue", "security", "access", "shortlink", "bot",
    "post_format", "storage_channel", "log_channel", "main_channel",
    "index_channel", "thumbnail_channel", "ui", "localization",
)


def register(client: Client, container: Container) -> None:
    from kurosoden.shared.settings_ui import register_settings

    auth = AuthService(container)
    L = container.localizer.get

    def _allowed(q: CallbackQuery, permission: Permission) -> bool:
        user = getattr(q, "nf_user", None)
        return bool(user and auth.has_permission(user, permission))

    def _is_owner(q: CallbackQuery) -> bool:
        return auth.is_owner(getattr(q, "nf_user", None))

    def _admin_home(is_owner: bool) -> Screen:
        caption = f"{t(M.ADMIN_HOME_TITLE)}\n\n{t(M.ADMIN_HOME_INTRO)}"
        rows = [
            [(t(M.ADMIN_BTN_QUEUE), cb("queue", "view", 0)),
             (t(M.ADMIN_BTN_ANALYTICS), cb("admin", "analytics"))],
            [(t(M.ADMIN_BTN_STAFF), cb("admin", "staff")),
             (t(M.ADMIN_BTN_SETTINGS), cb("admin", "settings"))],
            [(t(M.ADMIN_BTN_APPROVALS), cb("approve", "panel"))],
        ]
        # Sensitive infrastructure (bot tokens, storage channel, broadcast) is
        # owner-only — non-owner admins never even see the buttons.
        if is_owner:
            rows.append([(t(M.ADMIN_BTN_BOTS), cb("admin", "bots")),
                         (t(M.ADMIN_BTN_STORAGE), cb("admin", "storage"))])
            rows.append([(t(M.ADMIN_BTN_BROADCAST), cb("admin", "broadcast"))])
        return Screen(caption=caption, image=_art(), keyboard=keyboard(*rows))

    @client.on_callback_query(filters.regex(r"^admin\|home"))
    async def _home(_: Client, q: CallbackQuery) -> None:
        if not _allowed(q, Permission.CONFIGURE):
            await q.answer(L(M.ACCESS_DENIED), show_alert=True)
            return
        await q.answer()
        await send_screen(client, q.message.chat.id, _admin_home(_is_owner(q)), old_msg=q.message)

    # ── Settings surface: the shared human-friendly engine ─────────────────────
    # The admin-home "Settings" button emits ``admin|settings``; the engine also
    # handles ``admin|set|home`` (Back-from-section) and ``admin|set|…`` taps. Its
    # hub Back button emits ``admin|home``, landing on the admin home above.
    # ``input_group=14`` is unused elsewhere on the admin client (groups 1–13 are
    # taken), so the settings edit-capture never fights review/batch/staff text
    # handlers. Callback handlers default to group 0.
    register_settings(
        client, container, "admin",
        _SETTINGS_ORDER,
        title=t(M.SETTINGS_HOME_TITLE),
        blurb=t(M.SETTINGS_HOME_INTRO),
        input_group=14,
    )

    # ── Queue view ─────────────────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^queue\|view"))
    async def _queue(_: Client, q: CallbackQuery) -> None:
        if not _allowed(q, Permission.QUEUE_DOWNLOADS):
            await q.answer(L(M.ACCESS_DENIED), show_alert=True)
            return
        from nekofetch.services.queue_service import QueueService
        from nekofetch.ui import progress

        await q.answer()
        rows = await QueueService(container).dashboard()
        if not rows:
            screen = Screen(caption=f"{t(M.QUEUE_TITLE)}\n\n{t(M.QUEUE_EMPTY)}",
                            image=_art(),
                            keyboard=keyboard([(t(M.BTN_BACK), cb("admin", "home"))]))
            await send_screen(client, q.message.chat.id, screen, old_msg=q.message)
            return
        blocks = [
            progress.queue_block_html(
                anime_title=r.anime_title, status=r.status, progress=r.progress,
                speed_bps=r.speed_bps, eta_seconds=r.eta_seconds,
                current_episode=r.current_episode, downloaded_bytes=r.downloaded_bytes,
                total_bytes=r.total_bytes, job_id=r.job_id,
            )
            for r in rows
        ]
        screen = Screen(
            caption=f"{t(M.QUEUE_TITLE)}\n\n" + "\n".join(blocks), image=_art(),
            keyboard=keyboard([(t(M.BTN_REFRESH), cb("queue", "view", 0)),
                               (t(M.BTN_BACK), cb("admin", "home"))]),
        )
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)

    # ── Analytics ──────────────────────────────────────────────────────────────
    @client.on_callback_query(filters.regex(r"^admin\|analytics"))
    async def _analytics(_: Client, q: CallbackQuery) -> None:
        if not _allowed(q, Permission.VIEW_ANALYTICS):
            await q.answer(L(M.ACCESS_DENIED), show_alert=True)
            return
        from nekofetch.services.analytics_service import AnalyticsService
        from nekofetch.ui import log_sections as S

        await q.answer()
        s = await AnalyticsService(container).dashboard()
        caption = S.dashboard_section(s, list(s.most_requested), _ts())
        screen = Screen(caption=caption, image=_art(),
                        keyboard=keyboard([(t(M.BTN_BACK), cb("admin", "home"))]))
        await send_screen(client, q.message.chat.id, screen, old_msg=q.message)


def _art():
    from nekofetch.ui.artwork import pick_artwork
    return pick_artwork()


def _ts() -> str:
    from nekofetch.core.timefmt import now_label
    return now_label()
