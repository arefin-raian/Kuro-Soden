"""Lelouch home-menu layout — the owner/admin/user split.

The request bot's start screen shows exactly the right buttons per audience:
  • plain user  → New Request · My Requests
  • non-owner admin → + Batch Work · My Profile (NOT Command)
  • owner        → + Batch Work · Command (the full war table)

Settings/Command/Profile never both appear, and none surface for a plain user.
These assert against the real ``screens.home`` builder.
"""

from __future__ import annotations

from kurosoden.bots.lelouch import screens as S
from kurosoden.shared import lelouch_voice as V


def _labels(screen):
    return [b.text for row in screen.keyboard.inline_keyboard for b in row]


def _datas(screen):
    return [b.callback_data for row in screen.keyboard.inline_keyboard for b in row]


def test_home_user_sees_only_request_buttons():
    screen = S.home("Suzaku", is_staff=False, is_admin=False)
    labels = _labels(screen)
    assert labels == [V.BTN_REQUEST, V.BTN_MY_REQUESTS]
    # A plain user must never see admin-only surfaces.
    assert V.BTN_BATCH not in labels
    assert V.BTN_ADMIN not in labels
    assert V.BTN_PROFILE not in labels
    # Settings and the Board are not top-level.
    assert V.BTN_SETTINGS not in labels
    assert V.BTN_QUEUE not in labels


def test_home_owner_sees_command():
    screen = S.home("Lelouch", is_staff=True, is_admin=True, is_owner=True)
    labels = _labels(screen)
    assert labels == [V.BTN_REQUEST, V.BTN_MY_REQUESTS, V.BTN_BATCH, V.BTN_ADMIN]
    # The owner gets Command, not the personal Profile button.
    assert V.BTN_PROFILE not in labels
    assert V.BTN_SETTINGS not in labels


def test_home_nonowner_admin_sees_profile_not_command():
    # A non-owner admin gets Batch + their personal Profile, never Command.
    screen = S.home("Kallen", is_staff=True, is_admin=True, is_owner=False)
    labels = _labels(screen)
    assert labels == [V.BTN_REQUEST, V.BTN_MY_REQUESTS, V.BTN_BATCH, V.BTN_PROFILE]
    assert V.BTN_ADMIN not in labels


def test_home_staff_non_admin_does_not_get_batch_or_command():
    # Staff who aren't admins see only the two request buttons.
    screen = S.home("Nunnally", is_staff=True, is_admin=False)
    labels = _labels(screen)
    assert labels == [V.BTN_REQUEST, V.BTN_MY_REQUESTS]
    assert V.BTN_BATCH not in labels
    assert V.BTN_ADMIN not in labels
    assert V.BTN_PROFILE not in labels


def test_home_request_button_routes_to_new_request():
    screen = S.home("x", is_staff=False, is_admin=False)
    datas = _datas(screen)
    assert "req|new" in datas
    assert any(d.startswith("req|mine") for d in datas)
