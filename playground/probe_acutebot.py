"""playground/probe_acutebot.py — exercise the @acutebot fetch flow.

Forces the multi-step state machine in ``nekofetch.providers.acute_bot``
(menu → pick → tap → info card → Information button → AniList verification)
AGAINST a real @acutebot conversation so you can see exactly what each
state transition does, with no SQL / no main-channel posts / no media
downloads. Use this whenever @acutebot's response format shifts.

Usage
-----
    python playground/probe_acutebot.py --title "Attack on Titan"
    python playground/probe_acutebot.py --title "Frieren" --no-photo
    python playground/probe_acutebot.py --title "Jujutsu Kaisen" --no-trace

Required env (same as the production entry point)
-------------------------------------------------
    TELEGRAM_API_ID, TELEGRAM_API_HASH
    TELEGRAM_USERBOT_ACCOUNTS JSON array (or TELEGRAM_USERBOT_SESSION fallback)
    SESSION_PATH  (default C:\\data\\sessions)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Make ``src/`` importable without packaging.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Load .env before any env reads — mirrors the production container's loader.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001 - dotenv is optional here
    pass

from nekofetch.providers.acute_bot import fetch_from_acutebot
from nekofetch.sources.telegram.userbot import UserbotPool


def _make_tracer(enabled: bool, prefix: str = "    "):
    """Return an ``on_step`` callback that prints each state transition."""
    if not enabled:
        return None

    def _on_step(line: str) -> None:
        print(prefix + line, flush=True)

    return _on_step


def _emit_result(meta: dict | None) -> None:
    if meta is None:
        print("\n❌ NO RESULT — @acutebot didn't respond within the poll window.")
        return
    print("\n✅ RESULT:")
    print(f"   title          = {meta.get('title')!r}")
    print(f"   romaji         = {meta.get('romaji')!r}")
    print(f"   format         = {meta.get('format')!r}")
    print(f"   status         = {meta.get('status')!r}")
    print(f"   rating         = {meta.get('score')!r}")
    print(f"   episodes       = {meta.get('episode_count')!r}")
    print(f"   first_aired    = {meta.get('first_aired')!r}")
    print(f"   last_aired     = {meta.get('last_aired')!r}")
    print(f"   runtime        = {meta.get('runtime')!r}")
    print(f"   genres         = {meta.get('genres')!r}")
    print(f"   poster_url     = {meta.get('poster_url')!r}")
    print()
    print(f"   anilist_id     = {meta.get('anilist_id')!r}")
    sel = meta.get("_acutebot_selection")
    print(f"   selection      = {sel!r}")
    print(f"   verified       = {meta.get('verified')!r}")
    if meta.get("verified"):
        print("\n   🔒 VERIFIED — Information button on the info card exposed")
        print("      the canonical AniList ID; this row is trustworthy.")
    else:
        print("\n   ⚠️  UNVERIFIED — couldn't extract an AniList ID from the")
        print("      Information button (likely acutebot silent-edit / missing button).")
        print("      Caller should weigh this; the consumer (bot_content) is fine")
        print("      with an unverified row — AniList will be re-queried separately.")


async def _run(args: argparse.Namespace) -> int:
    missing = [k for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH") if not os.getenv(k)]
    if missing:
        print("❌ missing env:", missing)
        return 2
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_path = os.environ.get("SESSION_PATH", r"C:\data\sessions")
    print(f"📦 booting UserbotPool from {session_path!r}")
    pool = UserbotPool.from_env(api_id, api_hash, session_path)

    # Photo directory lives under <project-root>/data/probe_photos — never
    # next to the Pyrogram session storage (which on this box resolves to
    # ``C:\\data`` and may be read-only). Create it up-front; fail loud if
    # we can't, instead of letting the download silently no-op later.
    photo_dir: str | None = None
    if not args.no_photo:
        photo_dir_path = ROOT / "data" / "probe_photos"
        try:
            photo_dir_path.mkdir(parents=True, exist_ok=True)
            test_file = photo_dir_path / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            photo_dir = str(photo_dir_path)
        except OSError as exc:
            print(f"❌ cannot create probe photo dir {photo_dir_path}: {exc}")
            return 3
    on_step = _make_tracer(args.trace)

    try:
        print(f"🔍  /anime {args.title!r}\n")
        meta = await fetch_from_acutebot(
            args.title,
            pool,
            photo_dir=photo_dir,
            on_step=on_step,
        )
    finally:
        await pool.close()

    _emit_result(meta)
    return 0 if meta is not None else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Probe the @acutebot fetch flow with step-by-step tracing.",
    )
    p.add_argument("--title", default="Attack on Titan",
                   help="Title to look up via @acutebot (default: 'Attack on Titan').")
    p.add_argument("--no-photo", action="store_true",
                   help="Skip downloading the info-card photo to disk.")
    p.add_argument("--no-trace", dest="trace", action="store_false",
                   help="Suppress the per-step trace output.")
    p.set_defaults(trace=True)
    return p.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_parse_args())))
