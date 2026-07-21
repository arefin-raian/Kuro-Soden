"""Tests for shared/admin_profile.py — time-slot parsing/formatting.

This pure logic underpins the slot-aware assignment engine, so its edge cases
(12-hour vs 24-hour, midnight wrap, noon/midnight, messy multi-line input) are
worth pinning down.
"""

from __future__ import annotations

from kurosoden.shared.admin_profile import (
    any_slot_covers,
    format_slots,
    format_time,
    in_slot,
    minutes_into_slot,
    parse_slot,
    parse_slots,
    parse_time,
)


# ── parse_time ────────────────────────────────────────────────────────────────

def test_parse_time_12h():
    assert parse_time("6:00 PM") == 18 * 60
    assert parse_time("6pm") == 18 * 60
    assert parse_time("10:30 PM") == 22 * 60 + 30
    assert parse_time("6:00 AM") == 6 * 60


def test_parse_time_noon_and_midnight():
    assert parse_time("12 AM") == 0            # midnight
    assert parse_time("12:00 PM") == 12 * 60   # noon
    assert parse_time("12:30 AM") == 30


def test_parse_time_24h():
    assert parse_time("18:00") == 18 * 60
    assert parse_time("0:30") == 30
    assert parse_time("24:00") == 0            # 24:00 → midnight


def test_parse_time_rejects_garbage():
    assert parse_time("nope") is None
    assert parse_time("13 PM") is None         # 13 invalid on 12h clock
    assert parse_time("6:99") is None


# ── parse_slot / parse_slots ──────────────────────────────────────────────────

def test_parse_slot_basic():
    assert parse_slot("6:00 PM - 8:00 PM") == [18 * 60, 20 * 60]


def test_parse_slot_wraps_midnight():
    # 10:30 PM – 12:30 AM → end < start, a valid wrapping slot.
    assert parse_slot("10:30 PM - 12:30 AM") == [22 * 60 + 30, 30]


def test_parse_slot_dash_variants_and_to():
    assert parse_slot("6pm – 8pm") == [18 * 60, 20 * 60]     # en dash
    assert parse_slot("6pm to 8pm") == [18 * 60, 20 * 60]    # "to"


def test_parse_slot_rejects_zero_length_and_malformed():
    assert parse_slot("6pm - 6pm") is None
    assert parse_slot("just one time") is None


def test_parse_slots_multiline_skips_bad_lines():
    text = "• 6:00 PM - 8:00 PM\n• 10:30 PM - 12:30 AM\ngarbage line"
    assert parse_slots(text) == [[18 * 60, 20 * 60], [22 * 60 + 30, 30]]


def test_parse_slots_empty():
    assert parse_slots("") == []
    assert parse_slots(None) == []


# ── format ────────────────────────────────────────────────────────────────────

def test_format_time_roundish():
    assert format_time(18 * 60) == "6:00 PM"
    assert format_time(0) == "12:00 AM"
    assert format_time(12 * 60) == "12:00 PM"
    assert format_time(22 * 60 + 30) == "10:30 PM"


def test_format_slots():
    assert format_slots([[18 * 60, 20 * 60]]) == "6:00 PM – 8:00 PM"
    assert format_slots([]) == "—"
    assert format_slots(None) == "—"


# ── coverage predicates ───────────────────────────────────────────────────────

def test_in_slot_normal():
    slot = [18 * 60, 20 * 60]
    assert in_slot(19 * 60, slot)
    assert not in_slot(20 * 60, slot)      # end exclusive
    assert not in_slot(17 * 60, slot)


def test_in_slot_wraps_midnight():
    slot = [22 * 60 + 30, 30]              # 22:30 → 00:30
    assert in_slot(23 * 60, slot)
    assert in_slot(10, slot)               # 00:10 is inside
    assert not in_slot(60, slot)           # 01:00 is outside


def test_any_slot_covers():
    slots = [[18 * 60, 20 * 60], [22 * 60 + 30, 30]]
    assert any_slot_covers(19 * 60, slots)
    assert any_slot_covers(10, slots)
    assert not any_slot_covers(15 * 60, slots)


def test_minutes_into_slot_handles_wrap():
    slot = [22 * 60 + 30, 30]              # starts 22:30
    assert minutes_into_slot(22 * 60 + 40, slot) == 10
    assert minutes_into_slot(10, slot) == (10 - (22 * 60 + 30)) % (24 * 60)
    assert minutes_into_slot(12 * 60, slot) is None   # outside
