"""Config-driven image-host mirror order (Phase 7, workstream F).

``backup_bytes`` mirrors an image onto every independent host so a restore
survives a single operator outage. The *order* hosts are tried is config-driven
(``bot.image_host_order``), but the result always records each host's URL in its
own field and ``BackupImage.primary`` picks catbox → telegraph → envs → source
regardless of the attempt order.

These pin the order resolver (unknown keys dropped, missing hosts appended) and
that every host is attempted, with the network stubbed so nothing is uploaded.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import kurosoden.shared.image_backup as ib
from kurosoden.shared.image_backup import _host_order, backup_bytes


def _container(order=None):
    return SimpleNamespace(
        config=SimpleNamespace(
            bot=SimpleNamespace(image_host_order=order),
            thumbnail_channel=SimpleNamespace(telegraph_access_token=""),
        ),
    )


def test_host_order_defaults_when_unset():
    assert _host_order(_container(None)) == ("catbox", "telegraph", "envs")


def test_host_order_respects_config():
    assert _host_order(_container(["envs", "catbox", "telegraph"])) == (
        "envs", "catbox", "telegraph",
    )


def test_host_order_drops_unknown_and_appends_missing():
    # "bogus" is dropped; only "envs" named, so catbox/telegraph are appended.
    assert _host_order(_container(["bogus", "envs"])) == (
        "envs", "catbox", "telegraph",
    )


@pytest.mark.asyncio
async def test_backup_bytes_attempts_every_host_in_order(monkeypatch):
    calls: list[str] = []

    async def fake_catbox(blob, mime, ext, source_url):
        calls.append("catbox")
        return "cat/url"

    async def fake_telegraph(container, blob, mime, source_url):
        calls.append("telegraph")
        return "tel/url"

    async def fake_envs(blob, mime, ext):
        calls.append("envs")
        return "envs/url"

    monkeypatch.setattr(ib, "_upload_catbox", fake_catbox)
    monkeypatch.setattr(ib, "_upload_telegraph", fake_telegraph)
    monkeypatch.setattr(ib, "_upload_envs", fake_envs)

    result = await backup_bytes(
        _container(["envs", "catbox", "telegraph"]), b"\xff\xd8data", mime="image/jpeg",
    )

    # Attempted in the configured order …
    assert calls == ["envs", "catbox", "telegraph"]
    # … but each URL lands in its own field, and primary still prefers catbox.
    assert result.catbox_url == "cat/url"
    assert result.telegraph_url == "tel/url"
    assert result.envs_url == "envs/url"
    assert result.primary == "cat/url"


@pytest.mark.asyncio
async def test_backup_bytes_empty_blob_is_noop(monkeypatch):
    called = False

    async def boom(*a, **k):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(ib, "_upload_catbox", boom)
    result = await backup_bytes(_container(), b"", mime="image/jpeg")
    assert result.primary is None
    assert called is False
