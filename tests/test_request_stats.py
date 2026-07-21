"""Tests for the real request statistics behind Command / The Board.

The old panels showed a single misleading "pending" figure. These cover the two
pieces that replaced it:

  * ``RequestRepository.counts_by_status`` — one grouped query, real live counts.
  * ``RequestService.stats`` — folds the several in-flight statuses into one
    ``working`` bucket and exposes ``total`` (the figure Command headlines).

The repo test is DB-backed (uses the ``session``/``sessionmaker`` fixtures); the
folding test is pure (a fake container whose ``pg_sessionmaker`` yields the test
sessionmaker), so it runs on the default SQLite backend too.
"""

from __future__ import annotations

import pytest

from kurosoden.tests.helpers import _create_request


pytestmark = pytest.mark.asyncio


async def _seed_mixed(session):
    """One request in each of several statuses; returns the sessionmaker's data."""
    await _create_request(session, code="REQ-0001", user_id=1, status="pending")
    await _create_request(session, code="REQ-0002", user_id=1, status="queued")
    await _create_request(session, code="REQ-0003", user_id=1, status="downloading")
    await _create_request(session, code="REQ-0004", user_id=1, status="published")
    await _create_request(session, code="REQ-0005", user_id=1, status="published")
    await _create_request(session, code="REQ-0006", user_id=1, status="rejected")
    await _create_request(session, code="REQ-0007", user_id=1, status="failed")


async def test_counts_by_status_is_real(session):
    from nekofetch.infrastructure.repositories.request_repo import RequestRepository

    await _seed_mixed(session)
    counts = await RequestRepository(session).counts_by_status()
    assert counts.get("pending") == 1
    assert counts.get("queued") == 1
    assert counts.get("downloading") == 1
    assert counts.get("published") == 2
    assert counts.get("rejected") == 1
    assert counts.get("failed") == 1


async def test_stats_folds_working_and_totals(session, sessionmaker):
    from types import SimpleNamespace

    from nekofetch.services.request_service import RequestService

    await _seed_mixed(session)

    # Minimal container: stats() only touches pg_sessionmaker.
    fake = SimpleNamespace(pg_sessionmaker=sessionmaker)
    stats = await RequestService(fake).stats()

    assert stats.total == 7
    assert stats.pending == 1
    # working = queued + downloading (+ processing/ready/approved, none here).
    assert stats.working == 2
    assert stats.published == 2
    assert stats.rejected == 1
    assert stats.failed == 1


async def test_stats_empty_is_all_zero(session, sessionmaker):
    from types import SimpleNamespace

    from nekofetch.services.request_service import RequestService

    fake = SimpleNamespace(pg_sessionmaker=sessionmaker)
    stats = await RequestService(fake).stats()
    assert stats.total == 0
    assert stats.working == 0
    assert stats.published == 0
