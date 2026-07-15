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

# Standalone: the project root is the kage/ package directory.
# Add the PARENT to sys.path so `from kage.shared...` resolves correctly
# (Python finds kage/ as a subdirectory of the parent on sys.path).
_HERE = Path(__file__).resolve().parent        # .../kage/
_PROJECT_ROOT = _HERE.parent                    # .../ (parent of kage/)
sys.path.insert(0, str(_PROJECT_ROOT))
os.chdir(str(_HERE))


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
