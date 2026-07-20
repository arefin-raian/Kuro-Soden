"""Durable image backup — mirror a post's images onto independent public hosts.

When the main channel is banned we rebuild every post byte-for-byte on a fresh
channel. That rebuild reads image URLs out of the DB, so those URLs must outlive
the original channel and the original CDN. A single host is a single point of
failure, so every image is mirrored to a **primary** host with a **fallback**:

    catbox.moe  (primary — permanent, anonymous, 200 MB cap)
      └─ telegra.ph/upload  (fallback — anonymous, smaller, different operator)
          └─ envs.sh        (last resort — anonymous, yet another operator)

:func:`backup_image` downloads the source bytes once, then tries each host in
order, returning every URL that sticks (and which host produced it). The caller
persists them so a later restore can prefer the mirror and, if even that is
gone, fall back to the next. Everything is best-effort: a total failure returns
a :class:`BackupImage` with all-``None`` mirrors rather than raising, so one dead
image never aborts a whole-channel backup.

:func:`backup_bytes` is the same mirror pipeline for bytes already in hand (e.g.
an admin-uploaded asset) — it skips the download step.
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
    envs_url: str | None = None

    @property
    def primary(self) -> str | None:
        """The best URL to rebuild from: mirrors first, then original source."""
        return (self.catbox_url or self.telegraph_url or self.envs_url
                or self.source_url or None)


_ENVS_ENDPOINT = "https://envs.sh"


async def _upload_envs(blob: bytes, mime: str, ext: str) -> str | None:
    """Push bytes to envs.sh (last-resort mirror). Returns the URL or None.

    envs.sh accepts an anonymous multipart ``file=`` POST and replies with the
    bare URL as plain text. Best-effort — any hiccup returns None.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as cli:
            r = await cli.post(
                _ENVS_ENDPOINT,
                files={"file": (f"post{ext}", blob, mime)},
            )
            r.raise_for_status()
        url = (r.text or "").strip()
    except Exception as exc:  # noqa: BLE001 — last-resort host, never raises
        log.warning("imgbackup.envs.failed", error=str(exc))
        return None
    if url.startswith("https://") and "envs.sh" in url:
        log.info("imgbackup.envs.ok", url=url, bytes=len(blob))
        return url
    log.warning("imgbackup.envs.bad_body", body=url[:200])
    return None


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


async def backup_bytes(
    container: Container, blob: bytes, *,
    mime: str = "image/jpeg", source_url: str = "",
) -> BackupImage:
    """Mirror image ``blob`` to catbox → telegraph → envs.sh, in order.

    The shared upload core for bytes already in hand (admin uploads) and for the
    tail of :func:`backup_image` (post-download). Pushes to every host so the
    restore path has independent copies; any field may be ``None`` if that host
    rejected the upload. ``source_url`` is recorded (may be empty for a fresh
    upload) as the final rebuild fallback. Never raises.
    """
    result = BackupImage(source_url=source_url)
    if not blob:
        return result
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

    # Last resort: envs.sh (a third, independent operator).
    result.envs_url = await _upload_envs(blob, mime, ext)

    return result


async def backup_image(container: Container, source_url: str) -> BackupImage:
    """Mirror ``source_url`` across every host (catbox → telegraph → envs.sh).

    Downloads the bytes once, then delegates to :func:`backup_bytes` so the
    restore path has independent copies. Returns a :class:`BackupImage`; any
    field may be ``None`` if that host rejected the upload. Never raises.
    """
    if not source_url:
        return BackupImage(source_url=source_url)

    fetched = await _download(source_url)
    if fetched is None:
        return BackupImage(source_url=source_url)
    blob, mime = fetched
    return await backup_bytes(container, blob, mime=mime, source_url=source_url)
