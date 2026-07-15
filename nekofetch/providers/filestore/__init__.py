"""Fstore (File Store) integration — link generation for external file-store bots.

Links follow the Fstore format:
  single:  t.me/{bot}?start={urlsafe_base64("get-{msg_id * abs(channel_id)}")}
  batch:   t.me/{bot}?start={urlsafe_base64("get-{start * abs(channel_id)}-{end * abs(channel_id)}")}

Bot usernames are cycled via round-robin (Redis counter) so that load is
distributed evenly across all configured bots.
"""

from nekofetch.providers.filestore.linkgen import build_fstore_link, pick_fstore_bot_rr

__all__ = ["build_fstore_link", "pick_fstore_bot_rr"]
