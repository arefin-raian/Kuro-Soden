"""Tests for ManagementService profile setters (Phase 2).

Country / timezone / daily-hours cap / weekday+weekend slots are what the
slot-aware assignment engine reads, so persisting and reading them back through
the AdminView must be lossless, and the hours cap must clamp to 1–24.
"""

from __future__ import annotations

import pytest

from kurosoden.shared.management_service import ManagementService

pytestmark = pytest.mark.asyncio


async def test_set_profile_roundtrips(sessionmaker):
    svc = ManagementService(sessionmaker)
    await svc.ensure_admin(500, name="Kallen")

    await svc.set_country(500, "Bangladesh")
    await svc.set_timezone(500, "Asia/Dhaka")
    await svc.set_max_hours(500, 3)
    await svc.set_slots(500, "weekday", [[1080, 1200]])          # 6–8 PM
    await svc.set_slots(500, "weekend", [[1350, 30]])            # 10:30 PM–12:30 AM

    v = await svc.get_admin(500)
    assert v.country == "Bangladesh"
    assert v.timezone == "Asia/Dhaka"
    assert v.max_hours_per_day == 3
    assert v.slots_weekday == [[1080, 1200]]
    assert v.slots_weekend == [[1350, 30]]


async def test_max_hours_clamps(sessionmaker):
    svc = ManagementService(sessionmaker)
    await svc.ensure_admin(501)
    await svc.set_max_hours(501, 99)
    assert (await svc.get_admin(501)).max_hours_per_day == 24
    await svc.set_max_hours(501, 0)
    assert (await svc.get_admin(501)).max_hours_per_day == 1


async def test_set_profile_bulk_and_name_fill(sessionmaker):
    svc = ManagementService(sessionmaker)
    await svc.ensure_admin(502)                                  # no name yet
    v = await svc.set_profile(502, name="Lelouch", country="Japan",
                              max_hours_per_day=4)
    assert v.name == "Lelouch"          # filled a blank name
    assert v.country == "Japan"
    assert v.max_hours_per_day == 4
    # A later bulk set must NOT clobber an existing name.
    v2 = await svc.set_profile(502, name="Someone Else", country="Britannia")
    assert v2.name == "Lelouch"
    assert v2.country == "Britannia"


async def test_clear_slots(sessionmaker):
    svc = ManagementService(sessionmaker)
    await svc.ensure_admin(503)
    await svc.set_slots(503, "weekday", [[1080, 1200]])
    await svc.set_slots(503, "weekday", [])
    assert (await svc.get_admin(503)).slots_weekday == []
