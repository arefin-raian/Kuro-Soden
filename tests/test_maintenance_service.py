"""Coverage for ``MaintenanceService`` — the monthly ban check + update sweep.

Two orchestration jobs Gojo runs (scheduled monthly and on demand):

  • ``probe_channels`` — cheap ``get_chat`` liveness probe over every
    distribution channel plus the main channel. Only a recognized "gone" error
    (``CHANNEL_INVALID`` etc.) counts as banned; a transient blip must not.
  • ``scan_updates`` — a *detect-only* franchise sweep that surfaces finished
    entries not yet published, without touching the queue.

These pin the probe classification and the target set (channels + main, bots
skipped) so a false recovery can't be triggered by a network hiccup.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nekofetch.services.maintenance_service import (
    BanCheckResult,
    ChannelProbe,
    MaintenanceService,
)


class _FakeClient:
    """Admin-client stub: raise per chat_id, otherwise resolve fine."""

    def __init__(self, errors: dict[int, Exception]):
        self._errors = errors
        self.seen: list[int] = []

    async def get_chat(self, chat_id: int):
        self.seen.append(chat_id)
        exc = self._errors.get(chat_id)
        if exc is not None:
            raise exc
        return SimpleNamespace(id=chat_id)


def _container(sessionmaker, client, *, main_channel_id: int = 0):
    return SimpleNamespace(
        pg_sessionmaker=sessionmaker,
        admin_client=client,
        config=SimpleNamespace(
            main_channel=SimpleNamespace(channel_id=main_channel_id),
        ),
    )


async def _make_channel(session, *, chat_id: int, anime_doc_id: str | None,
                        name: str = "Ch"):
    from nekofetch.infrastructure.database.postgres.models import DistributionBot

    ch = DistributionBot(
        name=name, username=None, anime_doc_id=anime_doc_id,
        encrypted_token="fake", enabled=True, is_channel=True, chat_id=chat_id,
    )
    session.add(ch)
    await session.commit()
    return ch


# ── probe_channels ────────────────────────────────────────────────────────────

class TestProbeChannels:
    async def test_no_client_returns_empty(self, sessionmaker, session):
        svc = MaintenanceService(_container(sessionmaker, None))
        result = await svc.probe_channels()
        assert isinstance(result, BanCheckResult)
        assert result.checked == 0
        assert result.banned == []

    async def test_healthy_channel_not_flagged(self, sessionmaker, session):
        await _make_channel(session, chat_id=-1001, anime_doc_id="anilist:1")
        svc = MaintenanceService(_container(sessionmaker, _FakeClient({})))
        result = await svc.probe_channels()
        assert result.checked == 1
        assert result.banned == []

    async def test_ban_marker_flags_channel(self, sessionmaker, session):
        await _make_channel(session, chat_id=-1002, anime_doc_id="anilist:2",
                            name="Down One")
        client = _FakeClient({-1002: Exception("CHANNEL_INVALID: gone")})
        svc = MaintenanceService(_container(sessionmaker, client))
        result = await svc.probe_channels()
        assert result.checked == 1
        assert len(result.banned) == 1
        probe = result.banned[0]
        assert probe.anime_doc_id == "anilist:2"
        assert probe.reachable is False
        assert probe.name == "Down One"

    async def test_transient_error_not_flagged(self, sessionmaker, session):
        """A network blip (no ban marker) must not trigger a false recovery."""
        await _make_channel(session, chat_id=-1003, anime_doc_id="anilist:3")
        client = _FakeClient({-1003: Exception("Connection reset by peer")})
        svc = MaintenanceService(_container(sessionmaker, client))
        result = await svc.probe_channels()
        assert result.checked == 1
        assert result.banned == []

    async def test_main_channel_probed_when_configured(self, sessionmaker, session):
        client = _FakeClient({-100999: Exception("USER_BANNED")})
        svc = MaintenanceService(
            _container(sessionmaker, client, main_channel_id=-100999))
        result = await svc.probe_channels()
        assert -100999 in client.seen
        assert len(result.banned) == 1
        # The main channel carries no anime_doc_id — it recovers via change-main.
        assert result.banned[0].anime_doc_id is None

    async def test_bots_are_skipped(self, sessionmaker, session, distribution_bot):
        """``distribution_bot`` fixture is a bot (is_channel False) — never probed."""
        client = _FakeClient({})
        svc = MaintenanceService(_container(sessionmaker, client))
        result = await svc.probe_channels()
        assert result.checked == 0
        assert client.seen == []


# ── scan_updates (detect-only) ──────────────────────────────────────────────────

class TestScanUpdates:
    async def test_returns_only_actionable(self, sessionmaker, session, monkeypatch):
        """scan_updates filters check_all(create=False) down to entries with news."""
        from nekofetch.services import update_check_service as ucs_mod
        from nekofetch.services.update_check_service import CheckResult, NewEntry

        captured = {}

        async def fake_check_all(self, *, create=True):
            captured["create"] = create
            return [
                CheckResult(anime_doc_id="anilist:1", title="Empty", new_entries=[]),
                CheckResult(
                    anime_doc_id="anilist:2", title="Has News",
                    new_entries=[NewEntry(
                        anilist_id=9, format="TV", english_title="S2",
                        season_number=2, episode_count=12,
                    )],
                ),
            ]

        monkeypatch.setattr(ucs_mod.UpdateCheckService, "check_all", fake_check_all)
        svc = MaintenanceService(_container(sessionmaker, None))
        results = await svc.scan_updates()
        # Detect-only: never commits to the queue.
        assert captured["create"] is False
        assert len(results) == 1
        assert results[0].title == "Has News"


# ── dataclass shape ───────────────────────────────────────────────────────────

def test_channel_probe_defaults():
    p = ChannelProbe(anime_doc_id=None, chat_id=-1, name="x", reachable=True)
    assert p.error is None
