"""Section artwork — random selection with no back-to-back repeats.

Every major UI surface shows a 16:9 image. We rotate through the pool in
``images/`` randomly, but never return the same artwork twice in a row, so a
message that re-renders (e.g. an edit) doesn't keep showing the same picture.

Kuro Sōden: each bot character (levi / senku / gojo / lelouch) has its own
subdirectory under ``images/``. Pass ``bot_name`` to ``pick_artwork()`` to
pick from a character-specific pool; omit it for the shared default pool.
"""

from __future__ import annotations

import random
from pathlib import Path

# kage flattens the src/ layer — parents[2] reaches the project root
ART_DIR = Path(__file__).resolve().parents[2] / "images"


class ArtworkPicker:
    """Picks a random artwork, avoiding an immediate repeat of the last pick."""

    def __init__(self, directory: Path = ART_DIR) -> None:
        self.directory = directory
        self._last: Path | None = None

    def available(self) -> list[Path]:
        imgs = sorted(self.directory.glob("art_*.jpg"))
        return imgs or sorted(self.directory.glob("*.jpg"))

    def pick(self) -> Path | None:
        imgs = self.available()
        if not imgs:
            return None
        if len(imgs) == 1:
            self._last = imgs[0]
            return imgs[0]
        choices = [p for p in imgs if p != self._last]
        choice = random.choice(choices)
        self._last = choice
        return choice


# Module-level default so callers share the same no-repeat history.
_default = ArtworkPicker()
# Per-character pools (lazy, created on first use).
_pools: dict[str, ArtworkPicker] = {}


def pick_artwork(bot_name: str | None = None) -> Path | None:
    """Return the path to a random section artwork (never the same one twice
    consecutively), or ``None`` if the image pool is empty.

    When ``bot_name`` is given, picks from ``images/<bot_name>/`` first;
    falls back to the shared pool if the character directory is empty.
    """
    if bot_name:
        char_dir = ART_DIR / bot_name.lower()
        if char_dir.is_dir():
            if bot_name not in _pools:
                _pools[bot_name] = ArtworkPicker(char_dir)
            result = _pools[bot_name].pick()
            if result is not None:
                return result
    return _default.pick()
