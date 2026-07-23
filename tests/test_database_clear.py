"""Regression coverage for the owner-only database clear preserve set."""

from __future__ import annotations


def test_database_clear_preserves_identity_and_admin_profiles():
    from kurosoden.shared.database_clear import KEEP_TABLES

    assert "users" in KEEP_TABLES
    assert "admin_availability" in KEEP_TABLES
    assert "alembic_version" in KEEP_TABLES
    assert "admin_assignments" not in KEEP_TABLES
    assert "requests" not in KEEP_TABLES
    assert "download_queue" not in KEEP_TABLES


def test_lelouch_owner_menu_exposes_clear_database_only_to_owner_tier():
    from kurosoden.shared.command_menu import _TIERS

    user, staff, owner = _TIERS["lelouch"]
    assert all(cmd.command != "cleardatabase" for cmd in user)
    assert all(cmd.command != "cleardatabase" for cmd in staff)
    assert any(cmd.command == "cleardatabase" for cmd in owner)
