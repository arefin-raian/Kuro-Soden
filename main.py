"""Kuro Sōden (黒送伝) — The Dark Relay Pipeline entry point.

Boots the NekoFetch container (shared DB/cache/config), then starts all four
pipeline bots on a single event loop:

    Lelouch Vi Britannia  —  Request Bot   (request intake, dedup, admin assignment)
    Levi Ackerman         —  Downloader Bot (source selection, download, processing)
    Senku Ishigami        —  Distribution Bot (channel creation, content generation)
    Gojo Satoru           —  Publisher Bot  (main channel, index, recovery)

Kuro Sōden is a STANDALONE repository — NekoFetch's source is vendored under
kage/nekofetch/ so no external imports are needed.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

# Standalone: the project has a FLAT layout — ``docs/``, ``bots/``,
# ``shared/``, ``nekofetch/``, ``tests/`` all live at the repo root. Python
# imports use the prefix ``kage.<sub>`` (legacy of when this was a sub-folded
# repo called ``kage/`` inside ``NekoFetch/``). The handoff below registers a
# synthetic ``kage`` namespace whose subpackages map back to the real dirs
# via ``__path__`` shims — so ``from kage.shared.X import Y`` resolves to
# ``./shared/X.py`` regardless of where the project is unpacked (parented
# locally, or at ``/app/`` on Render / Railway).
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                  # /app/ — picks up top-level
                                                 # packages like ``nekofetch``
os.chdir(str(_HERE))

# ── ``kage`` namespace alias ─────────────────────────────────────────────────
# Register ``kage`` and its top-level subpackages as lightweight ``ModuleType``
# shims whose ``__path__`` points at the real directories. Once these entries
# are in ``sys.modules``, Python's normal importer resolves
# ``kage.<sub>.<mod>`` by searching ``__path__`` exactly as it would for any
# regular package — no more fragile parent-directory sys.path manipulation.
#
# Caveat (theoretical, not active here): if any code ever does BOTH
# ``from shared.X import ...`` and ``from kage.shared.X import ...``, Python
# will cache them as two distinct module objects. The kage codebase uniformly
# uses the ``kage.`` prefix, so this is inert. If that ever changes, switch to
# git-tracked symlinks or rename the project root to a ``kage/`` sub-folder.
import types as _types
_kage = _types.ModuleType("kage")
_kage.__path__ = [str(_HERE)]
sys.modules["kage"] = _kage
for _sub in ("shared", "bots", "nekofetch", "tests"):
    if (_HERE / _sub / "__init__.py").is_file():
        _shim = _types.ModuleType(f"kage.{_sub}")
        _shim.__path__ = [str(_HERE / _sub)]
        sys.modules[f"kage.{_sub}"] = _shim
# ────────────────────────────────────────────────────────────────────────────


async def _run() -> None:
    from nekofetch.core.config import get_env, get_app_config
    from nekofetch.core.logging import configure_logging, get_logger
    from nekofetch.core.container import Container

    env = get_env()
    configure_logging(level=env.log_level, json=env.log_json)
    log = get_logger("kage")

    container = Container.create()
    await container.startup()

    # Register Kage's ORM models so ``Base.metadata.create_all()`` and
    # Alembic pick up ``admin_assignments`` + ``admin_availability``.
    import kage.shared.models  # noqa: F401

    # Build stamp for restart verification.
    import subprocess as _sp

    def _build_id() -> str:
        try:
            out = _sp.run(
                ["git", "-C", str(_HERE), "log", "-1", "--format=%h %cd",
                 "--date=format:%Y-%m-%d %H:%M"],
                capture_output=True, text=True, timeout=5,
            )
            return out.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    from nekofetch import __version__ as _ver

    build = _build_id()
    log.info("kuro-soden.starting", version=_ver, build=build)
    print(f"\n  Kuro Sōden {_ver}  ·  build {build}  ·  4-bot pipeline\n", flush=True)

    # ── Pipeline manager ──────────────────────────────────────────────────────
    from kage.shared.pipeline_manager import PipelineManager

    manager = PipelineManager(container)
    stop = asyncio.Event()

    def _signal_handler() -> None:
        log.info("kuro-soden.stopping")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:  # Windows
            pass

    try:
        await manager.start()
        await stop.wait()
    finally:
        await manager.stop()
        await container.shutdown()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
