"""Phase 4 — index bullet de-duplication + universal footer edit.

Two independent fixes:
  • ``_strip_bullet`` / ``_letter_caption`` never emit a doubled ``⦿ ⦿`` when a
    title already carries a leading bullet (seeded empty cards, legacy titles).
  • ``FooterService.set_footer`` rewrites every stored footer row, bumps each
    affected bot's ``content_revision``, and persists the config template — so
    one edit reaches every distribution channel.
"""

from __future__ import annotations

import pytest

from nekofetch.services.index_channel_service import _letter_caption, _strip_bullet


# ── bullet de-duplication ────────────────────────────────────────────────────

def test_strip_bullet_removes_leading_glyph():
    assert _strip_bullet("⦿ Naruto") == "Naruto"
    assert _strip_bullet("  ⦿   Bleach") == "Bleach"
    assert _strip_bullet("One Piece") == "One Piece"


def test_letter_caption_no_double_bullet_when_title_prefixed():
    cap = _letter_caption("N", ["⦿ Naruto", "Nana"])
    # Each rendered line has exactly one bullet — never "⦿ ⦿".
    assert "⦿ ⦿" not in cap
    assert "<b>⦿ Naruto</b>" in cap
    assert "<b>⦿ Nana</b>" in cap


def test_letter_caption_empty_keeps_single_bullet():
    cap = _letter_caption("Q", [])
    assert "<b>⦿</b>" in cap
    assert "⦿ ⦿" not in cap


# ── universal footer edit ────────────────────────────────────────────────────

class _FooterRow:
    def __init__(self, bot_id, caption):
        self.bot_id = bot_id
        self.post_type = "footer"
        self.caption = caption


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Minimal async session: returns footer rows on select, records updates."""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []
        self.committed = False

    async def execute(self, stmt):
        self.executed.append(stmt)
        # First execute is the SELECT of footer rows; later ones are the UPDATE.
        if len(self.executed) == 1:
            return _Result(self._rows)
        return _Result([])

    async def commit(self):
        self.committed = True


class _SessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


class _FakeSettings:
    def __init__(self):
        self.calls = []

    async def set_value(self, section, field, value):
        self.calls.append((section, field, value))


@pytest.mark.asyncio
async def test_footer_service_rewrites_rows_and_bumps(monkeypatch):
    from nekofetch.services import footer_service as mod

    rows = [_FooterRow(1, "old"), _FooterRow(1, "old"), _FooterRow(2, "old")]
    session = _FakeSession(rows)

    monkeypatch.setattr(mod, "session_scope", lambda maker: _SessionCtx(session))

    # Stub SettingsService so no real config/Mongo write happens.
    fake_settings = _FakeSettings()
    import nekofetch.services.settings_service as ss
    monkeypatch.setattr(ss, "SettingsService", lambda c: fake_settings)

    class _C:
        pg_sessionmaker = object()

    result = await mod.FooterService(_C()).set_footer("<b>New Footer</b>")

    assert result.ok is True
    assert result.footers_rewritten == 3          # every footer row rewritten
    assert result.bots_bumped == 2                # two distinct bots
    assert all(r.caption == "<b>New Footer</b>" for r in rows)
    assert session.committed is True
    # config template persisted for future posts
    assert ("bot", "footer_text", "<b>New Footer</b>") in fake_settings.calls


@pytest.mark.asyncio
async def test_footer_service_rejects_empty(monkeypatch):
    from nekofetch.services import footer_service as mod

    class _C:
        pg_sessionmaker = object()

    result = await mod.FooterService(_C()).set_footer("   ")
    assert result.ok is False
    assert result.footers_rewritten == 0
