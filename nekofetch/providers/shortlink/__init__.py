"""Pluggable URL-shortener seam used to gate token generation.

A provider wraps a target URL (a bot deep link) in a monetized/short link the user must
visit. Implement a new provider by subclassing :class:`ShortlinkProvider`; selection is
by ``shortlink.provider`` in config. Built-in adapters ship for AroLinks and VPLinks.
"""

from nekofetch.providers.shortlink.base import NullShortlinkProvider, ShortlinkProvider

__all__ = ["ShortlinkProvider", "NullShortlinkProvider"]
