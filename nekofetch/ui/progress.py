from __future__ import annotations

import asyncio
import html

from pyrogram.enums import ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import Message

from nekofetch.core.constants import BAR_EMPTY, BAR_FILLED
from nekofetch.localization.messages import M, t


def bar(percent: float, *, width: int = 10) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = round(percent / 100 * width)
    return f"{BAR_FILLED * filled}{BAR_EMPTY * (width - filled)} {int(percent)}%"


def labeled(label: str, percent: float, *, width: int = 10) -> str:
    return f"{label}\n\n{bar(percent, width=width)}"


def labeled_html(label: str, percent: float, *, width: int = 10) -> str:
    return (
        f"<blockquote><b>{label}</b>\n\n"
        f"<b>{bar(percent, width=width)}</b></blockquote>"
    )


async def loading_animation(msg: Message, label: str, steps: int = 3, delay: float = 0.35) -> None:
    for i in range(1, steps + 1):
        try:
            await msg.edit_text(f"<b>{label}{'!' * i}</b>", parse_mode=ParseMode.HTML)
        except MessageNotModified:
            pass
        await asyncio.sleep(delay)


SPINNER = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
SPINNER_DONE = "✓"  # settled frame so the loader never freezes mid-spin


async def _safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


async def animate_until(
    msg: Message,
    awaitable,
    render,
    *,
    cadence: float = 0.12,
):
    """Keep ``msg`` visibly alive (cycling spinner) until ``awaitable`` resolves.

    ``render(frame)`` returns the HTML caption for a given spinner frame. The
    awaited result is returned. Telegram flood/edit errors are swallowed — the
    animation is cosmetic and must never break the actual operation.

    The first frame is painted immediately (so even a sub-cadence operation shows
    the loader), the spinner ticks quickly, and on completion a settled ``✓`` frame
    is painted in a ``finally`` so the message never freezes on a random mid-cycle
    glyph if the awaitable finishes early, errors, or is cancelled.
    """
    task = asyncio.ensure_future(awaitable)
    frame = 0
    await _safe_edit(msg, render(SPINNER[0]))   # paint immediately
    try:
        while not task.done():
            await asyncio.sleep(cadence)
            frame += 1
            await _safe_edit(msg, render(SPINNER[frame % len(SPINNER)]))
        return await task
    finally:
        await _safe_edit(msg, render(SPINNER_DONE))


async def staged_loading(msg: Message, stages: list[str], delay_per_stage: float = 0.4) -> None:
    for stage in stages:
        for dots in range(1, 4):
            try:
                await msg.edit_text(f"<b>{stage}{'!' * dots}</b>", parse_mode=ParseMode.HTML)
            except MessageNotModified:
                pass
            await asyncio.sleep(delay_per_stage / 3)


def queue_block_html(
    *,
    anime_title: str,
    status: str,
    progress: float,
    speed_bps: float,
    eta_seconds: int | None,
    current_episode: int | None = None,
    downloaded_bytes: int = 0,
    total_bytes: int = 0,
    job_id: int | None = None,
) -> str:
    bar_str = bar(progress)
    ep_line = f"\n<b>episode:</b> <b>S{current_episode:02d}</b>" if current_episode else ""
    size_line = ""
    if total_bytes > 0:
        size_line = (f"\n<b>size:</b> {human_bytes(downloaded_bytes)} / "
                     f"{human_bytes(total_bytes)}")
    id_line = f"  #{job_id}" if job_id else ""

    return (
        f"<blockquote>"
        f"📥 <b>{anime_title}</b>{id_line}"
        f"{ep_line}\n"
        f"<b>status:</b> {status}\n"
        f"<b>progress:</b> <b>{bar_str}</b>\n"
        f"<b>speed:</b> {human_speed(speed_bps)}\n"
        f"<b>eta:</b> {human_eta(eta_seconds)}"
        f"{size_line}"
        f"</blockquote>"
    )


def human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def human_speed(bps: float) -> str:
    return f"{human_bytes(bps)}/s"


def human_eta(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}h {m:02d}m"
    return f"{m:02d}m {s:02d}s"


def human_elapsed(seconds: int | None) -> str:
    """Compact elapsed clock: MM:SS, or HH:MM:SS once past an hour."""
    if seconds is None or seconds < 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def download_card_html(
    *,
    title: str,
    job_id: int,
    status: str,
    progress: float = 0.0,
    stage: str | None = None,
    season: int | None = None,
    current_episode: int | None = None,
    episode_index: int | None = None,
    total_episodes: int | None = None,
    resolution: str | None = None,
    audio: str | None = None,
    speed_bps: float = 0.0,
    downloaded_bytes: int = 0,
    total_bytes: int = 0,
    eta_seconds: int | None = None,
    elapsed_seconds: int | None = None,
    retry_attempt: int = 0,
    retry_max: int = 0,
    retry_reason: str | None = None,
    low_disk: bool = False,
) -> str:
    """Mobile-first live download card shown through Levi (no log channel here).

    One short fact per line so nothing wraps on a narrow phone: title+job, the
    episode, the variant, a stage line (Downloading / Retrying N/M), a 10-cell
    bar, then speed/size and ETA/elapsed paired two-per-line.
    """
    lines: list[str] = [t(M.DL_CARD_TITLE, title=_esc(title), job=job_id)]

    # Episode line — "S01E005 · 5 / 24"
    if current_episode is not None:
        of = ""
        if episode_index and total_episodes:
            of = f"  ·  {episode_index} / {total_episodes}"
        lines.append(t(M.DL_CARD_EP, season=(season or 1),
                       episode=current_episode, of=of))

    # Variant line — "1080p · DUAL"
    ver_bits = [b for b in (resolution, (audio or "").upper() or None) if b]
    if ver_bits:
        lines.append(t(M.DL_CARD_VER, ver=_esc(" · ".join(ver_bits))))

    lines.append("")  # blank spacer

    # Stage line — retrying takes priority so a stall is never silent.
    if retry_attempt and retry_max:
        reason = f" · {_esc(retry_reason)}" if retry_reason else ""
        lines.append(t(M.DL_CARD_STAGE_RETRYING, attempt=retry_attempt,
                       max=retry_max, reason=reason))
    elif stage and stage.lower() not in ("downloading", "download"):
        lines.append(t(M.DL_CARD_STAGE_GENERIC, stage=_esc(stage)))
    else:
        lines.append(t(M.DL_CARD_STAGE_DOWNLOADING))

    lines.append(f"<b>{bar(progress)}</b>")

    # speed · size  (only the parts we actually know)
    row1: list[str] = []
    if speed_bps > 0:
        row1.append(t(M.DL_CARD_STAT_SPEED, speed=_esc(human_speed(speed_bps))))
    if total_bytes > 0:
        row1.append(t(M.DL_CARD_STAT_SIZE, done=_esc(human_bytes(downloaded_bytes)),
                      total=_esc(human_bytes(total_bytes))))
    if row1:
        lines.append("   ·   ".join(row1))

    # eta · elapsed
    row2: list[str] = []
    if eta_seconds is not None:
        row2.append(t(M.DL_CARD_STAT_ETA, eta=_esc(human_eta(eta_seconds))))
    if elapsed_seconds is not None:
        row2.append(t(M.DL_CARD_STAT_ELAPSED, elapsed=_esc(human_elapsed(elapsed_seconds))))
    if row2:
        lines.append("   ·   ".join(row2))

    if low_disk:
        lines.append(t(M.DL_CARD_LOW_DISK))

    return "\n".join(lines)
