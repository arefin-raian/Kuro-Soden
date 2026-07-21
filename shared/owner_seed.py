"""Seed the owner as a first-class admin across the whole pipeline, on boot.

The owner (``security.owner_id`` or, failing that, the first ``ADMIN_IDS`` entry)
kept showing up as a plain user: not in the staff list, not an owner in the
access panel, and — the subtle one — **not in the admin pool**. That last gap
silently broke request routing: :meth:`AdminAssignmentEngine.assign` only creates
a task row when it finds an admin whose profile covers that stage and who is
within working hours. With nobody in the pool, ``assign("levi")`` returned
``None`` and *no* :class:`AdminAssignment` row was written, so Levi's task list —
which reads assignments — was empty even though the request sat QUEUED in the DB.
That is the "open downloader → no download task" report.

Seeding the owner fixes both faces of the problem at once:

  * ``users`` row exists with role ADMIN → owner appears in staff/admin lists.
  * ``admin_availability`` row exists, all four stages enabled, always-on hours,
    available → :meth:`assign` always finds at least the owner, so every stage
    hands off to a real task row and nothing is silently dropped.

Idempotent: run on every boot. It never *downgrades* an existing row (an owner
who narrowed their own stages/hours keeps them) — it only fills what's missing.
"""

from __future__ import annotations

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger

log = get_logger(__name__)


def _owner_id(container: Container) -> int | None:
    """The owner's Telegram id: ``security.owner_id`` if set, else ADMIN_IDS[0]."""
    configured = int(getattr(container.config.security, "owner_id", 0) or 0)
    if configured:
        return configured
    admin_ids = list(getattr(container.env, "admin_ids", []) or [])
    return int(admin_ids[0]) if admin_ids else None


async def seed_owner(container: Container) -> None:
    """Ensure the owner exists as an ADMIN user and a full-coverage pool admin.

    Best-effort: any failure is logged and swallowed so a seeding hiccup never
    blocks startup (the bot must still come up).
    """
    owner_id = _owner_id(container)
    if owner_id is None:
        log.warning("owner_seed.no_owner_id")
        return

    # ── 1. users row with ADMIN role ───────────────────────────────────────────
    try:
        from nekofetch.domain.enums import Role
        from nekofetch.infrastructure.database.postgres.session import session_scope
        from nekofetch.infrastructure.repositories.user_repo import UserRepository

        async with session_scope(container.pg_sessionmaker) as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(owner_id)
            if user is None:
                from nekofetch.infrastructure.database.postgres.models import User

                user = User(telegram_id=owner_id, role=Role.ADMIN, first_name="Owner")
                await repo.add(user)
            elif user.role != Role.ADMIN:
                user.role = Role.ADMIN
    except Exception as exc:  # noqa: BLE001
        log.warning("owner_seed.user_failed", owner=owner_id, error=str(exc))

    # ── 2. admin_availability row: all stages, always-on, available ────────────
    try:
        from kurosoden.shared.management_service import STAGES, ManagementService

        svc = ManagementService(container.pg_sessionmaker)
        existing = await svc.get_admin(owner_id)
        await svc.ensure_admin(owner_id, name="Owner")
        # Only fill coverage when the owner has none yet — never clobber a
        # deliberately-narrowed set on a returning owner.
        if existing is None or not existing.assigned_bots:
            await svc.set_bots(owner_id, list(STAGES))
        log.info("owner_seed.done", owner=owner_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("owner_seed.pool_failed", owner=owner_id, error=str(exc))
