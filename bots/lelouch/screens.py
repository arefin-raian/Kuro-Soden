"""Lelouch screen builders — voice + state → :class:`Screen`.

Pure builders (no Telegram I/O) so the dispatcher in ``app.py`` stays a thin
router. Every card goes through :func:`nekofetch.ui.screens.card`, so all of
Lelouch's surfaces share one grammar: a Lelouch-voiced HTML caption (from
``shared.lelouch_voice``), an image that is never omitted (recurring Lelouch
art here; per-anime backdrops on the request/dedup/receipt cards built in the
request handler), and a callback keyboard.
"""

from __future__ import annotations

from nekofetch.ui.components import cb
from nekofetch.ui.screens import Screen, card
from kurosoden.shared import lelouch_voice as V

BOT = "lelouch"


def home(name: str, *, is_staff: bool = False, is_admin: bool = False) -> Screen:
    caption = f"{V.home_title(name)}\n\n{V.HOME_BODY}"
    rows = [[(V.BTN_REQUEST, cb("req", "new")),
             (V.BTN_MY_REQUESTS, cb("req", "mine", 0))]]
    if is_staff or is_admin:
        caption += f"\n\n{V.HOME_ADMIN_TAG}"
        rows.append([(V.BTN_BATCH, cb("batch", "new")),
                     (V.BTN_QUEUE, cb(BOT, "queue", 0))])
    row = [(V.BTN_SETTINGS, cb(BOT, "settings"))]
    if is_admin:
        row.append((V.BTN_ADMIN, cb(BOT, "admin")))
    rows.append(row)
    return card(caption, bot_name=BOT, buttons=rows)


def admin_panel(*, mode: str, requests_open: bool, pending: int,
                work_open: int) -> Screen:
    caption = V.admin_panel(mode, requests_open, pending, work_open)
    toggle = (V.BTN_PAUSE, cb(BOT, "reqtoggle")) if requests_open \
        else (V.BTN_RESUME, cb(BOT, "reqtoggle"))
    rows = [
        [toggle],
        [(V.BTN_PENDING, cb(BOT, "pending", 0)),
         (V.BTN_QUEUE, cb(BOT, "queue", 0))],
        [(V.BTN_MANAGE, cb(BOT, "manage")),
         (V.BTN_AVAIL, cb(BOT, "avail"))],
        [(V.BTN_HOURS, cb(BOT, "hours")),
         (V.BTN_SETTINGS, cb(BOT, "settings"))],
        [(V.BTN_HOME, cb(BOT, "home"))],
    ]
    return card(caption, bot_name=BOT, buttons=rows)


def queue(*, pending: int, work_open: int, back: str = "home") -> Screen:
    caption = V.queue_view(pending, work_open)
    return card(caption, bot_name=BOT,
                buttons=[[(V.BTN_HOME if back == "home" else V.BTN_BACK_ADMIN,
                           cb(BOT, back))]])


def _panel(body_title: str, body: str, back: str = "admin") -> Screen:
    caption = f"{V.ICON} <b>{body_title}</b>\n\n{body}"
    return card(caption, bot_name=BOT,
                buttons=[[(V.BTN_BACK_ADMIN, cb(BOT, back))]])


def manage() -> Screen:
    return _panel("Manage Ranks", V.MANAGE_BODY)


def availability() -> Screen:
    return _panel("Availability", V.AVAIL_BODY)


def working_hours() -> Screen:
    return _panel("Working Hours", V.HOURS_BODY)


def coming_soon(what: str, *, back: str = "admin") -> Screen:
    return card(V.coming_soon(what), bot_name=BOT,
                buttons=[[(V.BTN_BACK_ADMIN, cb(BOT, back))]])
