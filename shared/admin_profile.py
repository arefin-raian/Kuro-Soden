"""Admin profile helpers — parse/format time slots and the profile view.

An admin's profile (country, timezone, daily-hours cap, preferred time slots)
drives the slot-aware assignment engine. Slots are stored as ``[start_min,
end_min]`` minute-of-day pairs (0–1439) in the admin's OWN timezone; ``end <
start`` means the slot wraps past midnight (e.g. 22:30→00:30).

This module owns the pure conversions between what a human types
(``"6:00 PM - 8:00 PM"``, one per line) and that stored form, plus a couple of
"is now inside a slot" predicates the engine reuses. Kept free of Telegram and DB
so it unit-tests cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DAY = 24 * 60  # minutes in a day

# "6", "6:30", "6:00 PM", "18:00", "12:30am" … captured leniently; validated after.
_TIME_RE = re.compile(
    r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?\s*$", re.IGNORECASE
)


def parse_time(text: str) -> int | None:
    """Minute-of-day (0–1439) for a single clock time, or ``None`` if unparseable.

    Accepts 12-hour (``6:00 PM``, ``6pm``) and 24-hour (``18:00``, ``6``). A bare
    hour with no am/pm is taken literally as 24-hour. ``12 AM`` = 00:00,
    ``12 PM`` = 12:00 (the usual English convention people get wrong, handled
    explicitly)."""
    m = _TIME_RE.match(text or "")
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower().replace(".", "")
    if minute > 59:
        return None
    if ampm:  # 12-hour clock
        if hour < 1 or hour > 12:
            return None
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        else:  # pm
            hour = 12 if hour == 12 else hour + 12
    else:  # 24-hour clock
        if hour == 24:
            hour = 0
        if hour > 23:
            return None
    return hour * 60 + minute


def format_time(minute: int) -> str:
    """Render a minute-of-day back as a friendly 12-hour clock (``6:00 PM``)."""
    minute %= _DAY
    h, m = divmod(minute, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def parse_slot(line: str) -> list[int] | None:
    """Parse one ``"<start> - <end>"`` line into ``[start_min, end_min]``.

    The separator may be ``-``, ``–`` (en dash), ``—`` (em dash), or ``to``.
    ``end == start`` is rejected (a zero-length slot is a typo); ``end < start``
    is kept as-is and means the slot wraps past midnight."""
    if not line or not line.strip():
        return None
    parts = re.split(r"\s*(?:-|–|—|to)\s*", line.strip(), maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    start = parse_time(parts[0])
    end = parse_time(parts[1])
    if start is None or end is None or start == end:
        return None
    return [start, end]


def parse_slots(text: str) -> list[list[int]]:
    """Parse a multi-line block of slots. Lines that don't parse are skipped, so
    one bad line never loses the good ones. A leading bullet (``•``, ``*``, ``·``)
    is stripped; a leading ``-`` is left alone so a range like ``6-8pm`` on its
    own line still parses."""
    out: list[list[int]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line[:1] in ("•", "*", "·"):
            line = line[1:].strip()
        slot = parse_slot(line)
        if slot is not None:
            out.append(slot)
    return out


def format_slots(slots: list[list[int]] | None) -> str:
    """Render stored slots as friendly lines (``6:00 PM – 8:00 PM``)."""
    if not slots:
        return "—"
    return "\n".join(
        f"{format_time(s)} – {format_time(e)}" for s, e in slots
    )


def in_slot(minute: int, slot: list[int]) -> bool:
    """Whether a minute-of-day falls inside one ``[start, end]`` slot, honouring
    midnight wrap (``end < start``)."""
    start, end = slot[0], slot[1]
    if start <= end:
        return start <= minute < end
    return minute >= start or minute < end  # wraps midnight


def any_slot_covers(minute: int, slots: list[list[int]] | None) -> bool:
    """True if any of ``slots`` covers ``minute``."""
    return any(in_slot(minute, s) for s in (slots or []))


def minutes_into_slot(minute: int, slot: list[int]) -> int | None:
    """How many minutes past a slot's start ``minute`` is, or ``None`` if outside.
    Handles midnight wrap so a 22:30→00:30 slot measures correctly at 00:10."""
    if not in_slot(minute, slot):
        return None
    start = slot[0]
    return (minute - start) % _DAY


@dataclass(slots=True)
class ProfileView:
    """A detached snapshot of an admin's profile for display."""

    country: str | None = None
    timezone: str | None = None
    max_hours_per_day: int | None = None
    slots_weekday: list | None = None
    slots_weekend: list | None = None
