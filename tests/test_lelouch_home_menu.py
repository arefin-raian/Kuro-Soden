"""Lelouch home-menu layout — the four-button contract (redesign).

The request bot's start screen must show exactly the four top-level buttons the
operator asked for — **New Request · My Requests** for everyone, plus **Batch
Work · Command** for admins only — and must NOT surface Settings or the Board at
the top level (Settings lives inside the Command panel, so it appears once).

These assert against the real ``screens.home`` builder, so a regression in the
button set or the admin gating fails here.
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
    # Settings and the Board are no longer top-level (Settings lives in Command).
    assert V.BTN_SETTINGS not in labels
    assert V.BTN_QUEUE not in labels


def test_home_admin_sees_four_buttons():
    screen = S.home("Lelouch", is_staff=True, is_admin=True)
    labels = _labels(screen)
    assert labels == [V.BTN_REQUEST, V.BTN_MY_REQUESTS, V.BTN_BATCH, V.BTN_ADMIN]
    # Still no top-level Settings — it is reached through Command.
    assert V.BTN_SETTINGS not in labels


def test_home_staff_non_admin_does_not_get_batch_or_command():
    # Batch Work and Command are admin-only per the redesign (previously Batch
    # leaked to any staff). A staff-but-not-admin user sees only the two request
    # buttons.
    screen = S.home("Kallen", is_staff=True, is_admin=False)
    labels = _labels(screen)
    assert labels == [V.BTN_REQUEST, V.BTN_MY_REQUESTS]
    assert V.BTN_BATCH not in labels
    assert V.BTN_ADMIN not in labels


def test_home_request_button_routes_to_new_request():
    screen = S.home("x", is_staff=False, is_admin=False)
    datas = _datas(screen)
    assert "req|new" in datas
    assert any(d.startswith("req|mine") for d in datas)
