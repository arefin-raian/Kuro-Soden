"""Durable image backup — mirror a post's images onto independent public hosts.

When the main channel is banned we rebuild every post byte-for-byte on a fresh
channel. That rebuild reads image URLs out of the DB, so those URLs must outlive
the original channel and the original CDN. A single host is a single point of
failure, so every image is mirrored to a **primary** host with a **fallback**:

    catbox.moe  (primary — permanent, anonymous, 200 MB cap)
      └─ telegra.ph/upload  (fallback — anonymous, smaller, different operator)

:func:`backup_image` downloads the source bytes once, then tries each host in
order, returning the first URL that sticks (and which host produced it). The
caller persists both so a later restore can prefer the mirror and, if even that
is gone, fall back to the other. Everything is best-effort: a total failure
returns ``(None, None)`` rather than raising, so one dead image never aborts a
whole-channel backup.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

log = get_logger(__name__)

_TIMEOUT = 60.0


@dataclass(slots=True)
class BackupImage:
    """Where a single source image now lives, mirrored."""
    source_url: str
    catbox_url: str | None = None
    telegraph_url: str | None = None

    @property
    def primary(self) -> str | None:
        """The best URL to rebuild from: mirror first, then original source."""
        return self.catbox_url or self.telegraph_url or self.source_url or None


async def _download(source_url: str) -> tuple[bytes, str] | None:
    """Fetch ``source_url`` → (bytes, mime). None on any failure/empty body."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cli:
            r = await cli.get(source_url)
            r.raise_for_status()
            blob = r.content
    except Exception as exc:  # noqa: BLE001 — any transport hiccup → None
        log.warning("imgbackup.download.failed", url=source_url, error=str(exc))
        return None
    if not blob:
        return None
    mime = (r.headers.get("content-type") or "image/jpeg").split(";", 1)[0].strip()
    return blob, (mime or "image/jpeg")


async def backup_image(container: Container, source_url: str) -> BackupImage:
    """Mirror ``source_url`` to catbox (primary) and telegraph (fallback).

    Downloads the bytes once and pushes them to both hosts so the restore path
    has two independent copies. Returns a :class:`BackupImage`; any field may be
    ``None`` if that host rejected the upload. Never raises.
    """
    result = BackupImage(source_url=source_url)
    if not source_url:
        return result

    fetched = await _download(source_url)
    if fetched is None:
        return result
    blob, mime = fetched
    ext = ".png" if mime == "image/png" else ".jpg"

    # Primary: catbox (upload the bytes we already hold, not urlupload).
    try:
        from nekofetch.providers.catbox import CatboxUploadError, upload_bytes

        result.catbox_url = await upload_bytes(
            blob, filename=f"post{ext}", mime_type=mime,
        )
    except (CatboxUploadError, httpx.HTTPError) as exc:
        log.warning("imgbackup.catbox.failed", url=source_url, error=str(exc))

    # Fallback: telegraph file host (independent operator).
    try:
        token = getattr(
            getattr(container.config, "thumbnail_channel", None),
            "telegraph_access_token", "",
        )
        from nekofetch.providers.metadata.telegraph_client import TelegraphClient

        client = TelegraphClient(token or "")
        result.telegraph_url = await client.upload_image(blob, mime_type=mime)
        await client.close()
    except Exception as exc:  # noqa: BLE001 — fallback is best-effort
        log.warning("imgbackup.telegraph.failed", url=source_url, error=str(exc))

    return result
