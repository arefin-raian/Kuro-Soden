"""VPLinks shortlink adapter.

Wraps a target URL in a VPLinks monetized short link.
Requires your VPLinks API token (``shortlink.vplinks_api_key``).

API docs: https://vplink.in/api
Endpoint: https://vplink.in/api?api=TOKEN&url=URL&alias=Alias
Response:  {"status":"success","shortenedUrl":"..."} | {"status":"error","message":"..."}
"""

from __future__ import annotations

from urllib.parse import quote

from nekofetch.core.logging import get_logger
from nekofetch.providers.shortlink.base import ShortlinkProvider

log = get_logger(__name__)

_VPLINKS_API = "https://vplink.in/api"


class VPLinksProvider(ShortlinkProvider):
    name = "vplinks"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def create_short_link(self, target_url: str) -> str:
        if not self.api_key:
            log.warning("shortlink.vplinks.no_api_key")
            return target_url
        import httpx

        url = (
            f"{_VPLINKS_API}?api={quote(self.api_key)}"
            f"&url={quote(target_url)}"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "success":
                    return data["shortenedUrl"]
                log.warning("shortlink.vplinks.error", message=data.get("message"))
        except Exception as exc:
            log.warning("shortlink.vplinks.request_failed", error=str(exc))
        return target_url
