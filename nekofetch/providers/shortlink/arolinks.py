"""AroLinks shortlink adapter.

Wraps a target URL in an AroLinks monetized short link.
Requires your AroLinks API token (``shortlink.arolinks_api_key``).

API docs: https://arolinks.com/api
Endpoint: https://arolinks.com/api?api=TOKEN&url=URL&alias=Alias
Response:  {"status":"success","shortenedUrl":"..."} | {"status":"error","message":"..."}
"""

from __future__ import annotations

from urllib.parse import quote

from nekofetch.core.logging import get_logger
from nekofetch.providers.shortlink.base import ShortlinkProvider

log = get_logger(__name__)

_AROLINKS_API = "https://arolinks.com/api"


class AroLinksProvider(ShortlinkProvider):
    name = "arolinks"

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    async def create_short_link(self, target_url: str) -> str:
        if not self.api_key:
            log.warning("shortlink.arolinks.no_api_key")
            return target_url
        import httpx

        url = (
            f"{_AROLINKS_API}?api={quote(self.api_key)}"
            f"&url={quote(target_url)}"
        )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "success":
                    return data["shortenedUrl"]
                log.warning("shortlink.arolinks.error", message=data.get("message"))
        except Exception as exc:
            log.warning("shortlink.arolinks.request_failed", error=str(exc))
        return target_url
