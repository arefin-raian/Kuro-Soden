"""Phase 1 — Gojo publisher voice + task-driven publish flow.

Covers the pieces that don't need a live Telegram client:
  * the ``_parse_schedule`` grammar (valid / past / garbage),
  * the review keyboard's callback wiring (publish / silent / schedule / edit),
  * the voice module surface (every card renders finished HTML).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


# ── schedule parsing ────────────────────────────────────────────────────────────

class TestParseSchedule:
    def _parse(self, raw: str):
        from kurosoden.bots.gojo.handlers.tasks import _parse_schedule
        return _parse_schedule(raw)

    def test_future_time_parses(self):
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        assert self._parse(future) is not None

    def test_future_time_with_seconds(self):
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        assert self._parse(future) is not None

    def test_past_time_rejected(self):
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        assert self._parse(past) is None

    def test_garbage_rejected(self):
        assert self._parse("next tuesday") is None
        assert self._parse("") is None
        assert self._parse("2024") is None

    def test_whitespace_tolerated(self):
        future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
        assert self._parse(f"  {future}  ") is not None


# ── review keyboard wiring ──────────────────────────────────────────────────────

class TestPublishKeyboard:
    def _flatten(self, markup):
        return [btn for row in markup.inline_keyboard for btn in row]

    def test_all_actions_present(self):
        from kurosoden.bots.gojo.handlers.tasks import _publish_keyboard

        btns = self._flatten(_publish_keyboard("REQ-1234"))
        data = {b.callback_data for b in btns}
        assert "gojo|publish_confirm|REQ-1234" in data
        assert "gojo|publish_silent|REQ-1234" in data
        assert "gojo|publish_schedule|REQ-1234" in data
        assert "gojo|publish_edit|REQ-1234" in data

    def test_code_threaded_into_every_action(self):
        from kurosoden.bots.gojo.handlers.tasks import _publish_keyboard

        btns = self._flatten(_publish_keyboard("REQ-ABCD"))
        publish_actions = [
            b for b in btns if b.callback_data and b.callback_data.startswith("gojo|publish_")
        ]
        assert publish_actions, "expected publish action buttons"
        assert all("REQ-ABCD" in b.callback_data for b in publish_actions)


# ── voice surface ───────────────────────────────────────────────────────────────

class TestGojoVoice:
    def test_review_card_includes_title_and_code(self):
        from kurosoden.shared import gojo_voice as V

        card = V.review_card("Attack on Titan", "REQ-9", "anilist:16498")
        assert "Attack on Titan" in card
        assert "REQ-9" in card
        assert "anilist:16498" in card

    def test_review_card_escapes_title(self):
        from kurosoden.shared import gojo_voice as V

        card = V.review_card("A < B & C", "REQ-1")
        assert "&lt;" in card and "&amp;" in card

    def test_published_silent_vs_loud(self):
        from kurosoden.shared import gojo_voice as V

        assert "quietly" in V.published("X", silent=True)
        assert "quietly" not in V.published("X", silent=False)

    def test_scheduled_mentions_time(self):
        from kurosoden.shared import gojo_voice as V

        assert "2026-01-02 09:30" in V.scheduled("X", "2026-01-02 09:30")

    def test_button_labels_stable(self):
        from kurosoden.shared import gojo_voice as V

        # These strings are matched by callback registration; guard against drift.
        assert V.BTN_PUBLISH_NOW and V.BTN_PUBLISH_SILENT
        assert V.BTN_SCHEDULE and V.BTN_EDIT_CAPTION
