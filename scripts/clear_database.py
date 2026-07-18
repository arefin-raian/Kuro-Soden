"""Wipe ALL Kuro Sōden application state — Postgres + Mongo + Redis.

Standalone twin of NekoFetch's ``scripts/clear_database.py``, wired for Kuro
Sōden's OWN databases (the ``kage`` Postgres, the ``kuro_soden`` Mongo cluster,
and the dedicated Upstash Redis) — never NekoFetch's. Use it to reset to a clean
slate between test runs.

    python scripts/clear_database.py            # keeps users, asks to confirm
    python scripts/clear_database.py --yes      # keeps users, no prompt
    python scripts/clear_database.py --all      # ALSO wipes users
    python scripts/clear_database.py --all --yes

What it does:
  • Postgres — TRUNCATE every table (RESTART IDENTITY CASCADE). ``users`` and
    ``alembic_version`` are preserved unless ``--all`` is given.
  • Mongo    — empties every collection.
  • Redis    — FLUSHDB. Kuro Sōden owns its Redis instance outright (a different
    Upstash host than NekoFetch), so a full flush is safe and thorough — it
    beats chasing the ~19 distinct key prefixes (``nf:``, ``staff:``, ``req:``,
    ``wire:``, ``kurosoden:``, ``dist:``, ``batch:`` …) the pipeline uses.

The log-channel layout and index sections are self-healing, so clearing their
Redis/Postgres state is safe — they rebuild on the next startup.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

# ── ``kurosoden`` namespace bootstrap (mirrors main.py) ───────────────────────
# scripts/ lives one level under the repo root. Insert the root on sys.path,
# chdir into it (so ``get_env()`` reads Kuro Sōden's ``.env`` — NOT NekoFetch's
# from a parent directory), and register the synthetic ``kurosoden`` namespace so
# ``from kurosoden.shared.models import ...`` resolves to ``./shared/models.py``.
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(str(_HERE))

_kage = types.ModuleType("kurosoden")
_kage.__path__ = [str(_HERE)]
sys.modules["kurosoden"] = _kage
for _sub in ("shared", "bots", "nekofetch", "tests"):
    if (_HERE / _sub / "__init__.py").is_file():
        _shim = types.ModuleType(f"kurosoden.{_sub}")
        _shim.__path__ = [str(_HERE / _sub)]
        sys.modules[f"kurosoden.{_sub}"] = _shim
# ──────────────────────────────────────────────────────────────────────────────

_KEEP_TABLES = {"users", "alembic_version"}


async def main(assume_yes: bool, wipe_all: bool) -> None:
    from nekofetch.core.config import get_env

    env = get_env()
    scope = "EVERYTHING including users" if wipe_all else "all data except users"

    # Show which databases we're about to hit — cheap insurance against pointing
    # this at the wrong environment.
    print(f"  Target Postgres : {env.postgres_db} @ {env.postgres_host}")
    print(f"  Target Mongo    : {env.mongo_db}")
    print(f"  Target Redis    : {env.redis_url.split('@')[-1]}")
    print(f"  Scope           : {scope}\n")

    if not assume_yes:
        ans = input(f"This wipes {scope} (Postgres + Mongo + Redis). Type 'yes': ")
        if ans.strip().lower() != "yes":
            print("aborted")
            return

    from nekofetch.core.container import Container

    container = Container.create()
    await container.startup()

    # Register Kage's ORM tables (admin_assignments, admin_availability,
    # work_items) onto the shared Base.metadata so they get truncated too.
    import kurosoden.shared.models  # noqa: F401

    try:
        # ── Postgres: truncate every table (optionally keep users) ──
        from sqlalchemy import text

        from nekofetch.infrastructure.database.postgres.models import Base

        keep = set() if wipe_all else _KEEP_TABLES
        tables = [t.name for t in Base.metadata.sorted_tables if t.name not in keep]
        if tables and container.pg_engine is not None:
            async with container.pg_engine.begin() as conn:
                await conn.execute(
                    text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
                )
            kept = "nothing" if wipe_all else sorted(_KEEP_TABLES)
            print(f"postgres: truncated {len(tables)} table(s), kept {kept}")

        # ── Mongo: empty every collection ──
        if container.mongo is not None:
            names = await container.mongo.list_collection_names()
            for name in names:
                await container.mongo[name].delete_many({})
            print(f"mongo: cleared {len(names)} collection(s)")

        # ── Redis: flush the dedicated instance ──
        if container.redis is not None:
            await container.redis.flushdb()
            print("redis: flushed all keys (dedicated instance)")

        tail = "" if wipe_all else " (users preserved)"
        print(f"done — Kuro Sōden database cleared{tail}")
    finally:
        await container.shutdown()


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(assume_yes="--yes" in args, wipe_all="--all" in args))
