"""Catbox.moe file host — used as the cache backend for distribution-bot card images.

Why catbox.moe:
  * Free, anonymous, public API (no account/login required).
  * Permanent URLs (the file stays unless flagged for TOS violation).
  * Reasonable uptime for a small-scale media prep tool like NekoFetch.

Why we upload BYTES instead of using catbox's ``urlupload`` (which proxies the
remote URL):
  * TMDB and AniList CDNs block common datacenter / proxy IPs. ``urlupload``
    runs from catbox's infrastructure, which would frequently 403 against the
    same CDNs we already had to bypass in the rest of the sourcing code.
  * We can verify the bytes are non-empty before POSTing, so catbox always
    receives a valid image rather than a Cloudflare challenge page.
  * We control the extension on the multipart boundary (catbox preserves it),
    so the returned URL always has the right ``.jpg``/``.png`` suffix.

The returned URL is a public read-only HTTPS link with no download counter,
suitable for `bot_content.BotContentPost.image_cached_url` and consumed by the
distribution bot's read path on `/start`.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import httpx

from nekofetch.core.logging import get_logger

log = get_logger(__name__)

# Catbox endpoint. Anonymous upload (no userhash) — see https://catbox.moe/faq.php.
_ENDPOINT = "https://catbox.moe/user/api.php"
_TIMEOUT_SECONDS = 60.0
_MAX_BYTES = 200 * 1024 * 1024  # catbox hard cap: 200 MB per file.


class CatboxUploadError(Exception):
    """Raised when catbox returns a non-URL error response (e.g. 'File too large')."""


async def upload_bytes(
    file_bytes: bytes,
    *,
    filename: str = "card.jpg",
    mime_type: str = "image/jpeg",
    timeout: float = _TIMEOUT_SECONDS,
) -> str:
    """Upload ``file_bytes`` to catbox.moe and return the resulting public URL.

    Parameters
    ----------
    file_bytes : bytes
        The image content to upload. Empty bytes raise ``CatboxUploadError``
        up-front — there's no point bombing catbox with a zero-length file.
    filename : str
        The multipart filename. The extension is what catbox preserves in the
        returned URL, so ``"card.jpg"`` produces ``https://files.catbox.moe/xx.jpg``.
    mime_type : str
        Content-Type for the file part of the multipart body.

    Raises
    ------
    CatboxUploadError
        Catbox returned a non-URL response (size cap, malformed body, etc).
    httpx.HTTPError
        Network/transport failure (timeout, connection reset, ...).
    """
    if not file_bytes:
        raise CatboxUploadError("empty payload")
    if len(file_bytes) > _MAX_BYTES:
        raise CatboxUploadError(
            f"file too large ({len(file_bytes)} > {_MAX_BYTES} bytes)"
        )

    data = {"reqtype": "fileupload"}
    files = {"fileToUpload": (filename, file_bytes, mime_type)}

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
        resp = await cli.post(_ENDPOINT, data=data, files=files)

    text = (resp.text or "").strip()
    if text.startswith("https://files.catbox.moe/"):
        log.info("catbox.upload.ok", url=text, bytes=len(file_bytes))
        return text

    # Catbox returns 200 even on most errors; the body is a plain-text string
    # like "File too large." or "Invalid file." — surface it for the caller.
    log.warning("catbox.upload.failed", status=resp.status_code, body=text[:200])
    raise CatboxUploadError(text or f"HTTP {resp.status_code}")


async def upload_from_url(
    source_url: str,
    *,
    timeout: float = _TIMEOUT_SECONDS,
) -> str | None:
    """Download ``source_url`` then upload the bytes to catbox.

    Returns the catbox URL on success, ``None`` on any failure (network,
    parse, catbox rejection) — the caller decides whether falling back is
    appropriate. ``generate_posts`` swallows ``None`` so a single broken
    poster never blocks the whole regeneration.
    """
    if not source_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            r = await cli.get(source_url)
            r.raise_for_status()
            blob = r.content
    except Exception as exc:  # noqa: BLE001 - any transport hiccup → None
        log.warning("catbox.download.failed", url=source_url, error=str(exc))
        return None

    if not blob:
        log.warning("catbox.download.empty", url=source_url)
        return None

    # Best-effort content-type + filename, falling back to .jpg.
    mime = (r.headers.get("content-type") or "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    ext = PurePosixPath(source_url.split("?", 1)[0]).suffix.lower() or ".jpg"
    if mime == "image/jpeg" and ext == ".png":
        mime = "image/png"
    elif mime == "image/png" and ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"

    filename = f"card{ext}"
    try:
        return await upload_bytes(blob, filename=filename, mime_type=mime, timeout=timeout)
    except (CatboxUploadError, httpx.HTTPError) as exc:
        log.warning("catbox.upload_from_url.failed", url=source_url, error=str(exc))
        return None
