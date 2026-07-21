"""Tests for owner-seed's id resolution.

The seeding itself is DB + service wiring (exercised indirectly by startup); the
one piece with real branching logic is ``_owner_id`` — which source wins when
``security.owner_id`` is set vs. falling back to ``ADMIN_IDS[0]``. Pure, no DB.
"""

from __future__ import annotations

from types import SimpleNamespace

from kurosoden.shared.owner_seed import _owner_id


def _container(*, owner_id: int, admin_ids: list[int]):
    return SimpleNamespace(
        config=SimpleNamespace(security=SimpleNamespace(owner_id=owner_id)),
        env=SimpleNamespace(admin_ids=admin_ids),
    )


def test_configured_owner_id_wins():
    c = _container(owner_id=777, admin_ids=[111, 222])
    assert _owner_id(c) == 777


def test_falls_back_to_first_admin_id():
    c = _container(owner_id=0, admin_ids=[111, 222])
    assert _owner_id(c) == 111


def test_none_when_no_owner_and_no_admins():
    c = _container(owner_id=0, admin_ids=[])
    assert _owner_id(c) is None
