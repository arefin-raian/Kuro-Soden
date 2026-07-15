"""Duty Board — UI renderers for the admin shift rotation panel.

Renders the pinned duty board message that sits at the top of each channel,
plus the handoff summary DM and takeover/relief notification messages.
"""

from __future__ import annotations

import html
import time
from datetime import datetime, timezone

from nekofetch.domain.enums import ShiftStatus
from nekofetch.services.shift_service import HandoffSummary, ShiftState

_CHANNEL_LABEL = {
    "logcc": "Control Center",
    "thumbcc": "The Canvas",
}


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def _ts_fmt(unix: float) -> str:
    if not unix:
        return "—"
    dt = datetime.fromtimestamp(unix, tz=timezone.utc)
    return dt.strftime("%H:%M UTC")


def duty_board(state: ShiftState) -> str:
    """Render the duty board panel for a channel.

    Returns an HTML-formatted string suitable for a Telegram message.
    """
    label = _CHANNEL_LABEL.get(state.channel, state.channel.title())
    if state.worker_id is None:
        return (
            f"<b>🛡️ Duty Board — {_esc(label)}</b>\n"
            f"<i>{'─' * 20}</i>\n\n"
            f"⚪ <b>Available</b>\n"
            f"<i>No one is on duty. Tap a button to begin.</i>"
        )

    status_icon = {
        ShiftStatus.ACTIVE: "🟢",
        ShiftStatus.RELIEF_SOUGHT: "🟡",
        ShiftStatus.TAKEOVER_PENDING: "🔵",
    }.get(state.status, "⚪")

    status_text = {
        ShiftStatus.ACTIVE: "On Duty",
        ShiftStatus.RELIEF_SOUGHT: "Needs Relief",
        ShiftStatus.TAKEOVER_PENDING: "Takeover Requested",
    }.get(state.status, "Unknown")

    name = state.worker_name or f"Admin {state.worker_id}"
    since = _ts_fmt(state.started_at)

    lines = [
        f"<b>🛡️ Duty Board — {_esc(label)}</b>",
        f"<i>{'─' * 20}</i>",
        "",
        f"{status_icon} <b>{_esc(status_text)}</b>",
        f"   <b>{_esc(name)}</b> — since {since}",
    ]

    if state.status == ShiftStatus.TAKEOVER_PENDING and state.takeover_requester_name:
        lines += [
            "",
            f"🔵 <b>{_esc(state.takeover_requester_name)}</b> wants to take over.",
        ]

    return "\n".join(lines)


def handoff_dm(summary: HandoffSummary) -> str:
    """Build the DM sent to the new worker upon successful takeover."""
    label = _CHANNEL_LABEL.get(summary.channel, summary.channel.title())
    duration = ""
    if summary.started_at:
        mins = int((time.time() - summary.started_at) / 60)
        if mins > 0:
            duration = f" ({mins}m shift)"

    lines = [
        f"✅ <b>Shift Acquired: {_esc(label)}</b>",
        "",
        f"<b>Previous Worker:</b> {_esc(summary.previous_worker)}{duration}",
        "",
        "📊 <b>Current State</b>",
        f"   ⏳ Pending: {summary.pending_count} requests",
        f"   🔄 Active: {summary.active_count} jobs",
        f"   ✅ Completed today: {summary.completed_today}",
    ]

    if summary.notes:
        lines += [
            "",
            f"📝 <b>Notes from {_esc(summary.previous_worker)}:</b>",
            f"<blockquote>{_esc(summary.notes)}</blockquote>",
        ]

    lines += [
        "",
        "<i>You are now on duty. All control buttons are yours.</i>",
    ]

    return "\n".join(lines)


def takeover_request_dm(
    requester_name: str, channel: str,
) -> str:
    """DM sent to the current worker when someone requests a takeover."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"🔵 <b>Takeover Request — {_esc(label)}</b>\n\n"
        f"<b>{_esc(requester_name)}</b> wants to take over the shift.\n\n"
        f"<i>Choose an action below:</i>"
    )


def takeover_denied_dm(channel: str, worker_name: str) -> str:
    """DM sent to requester when takeover is denied."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"❌ <b>Takeover Denied — {_esc(label)}</b>\n\n"
        f"<b>{_esc(worker_name)}</b> declined your takeover request.\n"
        f"The current worker is still on duty."
    )


def relief_request_dm(worker_name: str, channel: str) -> str:
    """DM broadcast to all off-duty staff when relief is sought."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"🟡 <b>Relief Needed — {_esc(label)}</b>\n\n"
        f"<b>{_esc(worker_name)}</b> needs someone to take over the shift.\n\n"
        f"<i>First to accept claims it:</i>"
    )


def relief_claimed_dm(acceptor_name: str, channel: str) -> str:
    """Edit the relief DM to show it's been claimed."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"🟢 <b>Relief Claimed — {_esc(label)}</b>\n\n"
        f"<b>{_esc(acceptor_name)}</b> has taken over the shift.\n"
        f"<i>This request is now closed.</i>"
    )


def afk_release_dm(channel: str) -> str:
    """DM sent to the worker when auto-released for AFK."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"⏰ <b>Auto-Released — {_esc(label)}</b>\n\n"
        f"You've been automatically released from the {_esc(label)} shift\n"
        f"due to 45 minutes of inactivity. The channel is now available."
    )


def blocked_alert(worker_name: str, channel: str) -> str:
    """Inline alert shown when a non-worker clicks a button."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"🛡️ <b>{_esc(worker_name)}</b> is currently on duty in {_esc(label)}.\n\n"
        f"Tap <b>Request Takeover</b> to ask for the shift."
    )


def handoff_notes_prompt(channel: str) -> str:
    """Prompt for the outgoing worker to leave notes."""
    label = _CHANNEL_LABEL.get(channel, channel.title())
    return (
        f"📝 <b>Handoff Notes — {_esc(label)}</b>\n\n"
        f"You're handing off the {_esc(label)} shift.\n"
        f"Leave any notes for the next worker (e.g. current task, issues, tips),\n"
        f"or tap <b>Skip Notes</b> to hand off immediately.\n\n"
        f"<i>Reply to this message with your notes.</i>"
    )
