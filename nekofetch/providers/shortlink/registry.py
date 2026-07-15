"""Shortlink provider selection (by ``shortlink.provider`` in config)."""

from __future__ import annotations

from nekofetch.core.config import ShortlinkConfig
from nekofetch.providers.shortlink.base import NullShortlinkProvider, ShortlinkProvider


def build_shortlink_provider(cfg: ShortlinkConfig) -> ShortlinkProvider:
    if not cfg.enabled:
        return NullShortlinkProvider()
    if cfg.provider == "arolinks":
        from nekofetch.providers.shortlink.arolinks import AroLinksProvider

        return AroLinksProvider(api_key=cfg.arolinks_api_key)
    if cfg.provider == "vplinks":
        from nekofetch.providers.shortlink.vplinks import VPLinksProvider

        return VPLinksProvider(api_key=cfg.vplinks_api_key)
    # Unknown provider name -> no-op (returns target unchanged).
    return NullShortlinkProvider()
