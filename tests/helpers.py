"""Shared fixture factories for Kage tests.

These are used by both conftest.py (for pytest fixtures) and test files
(for inline test data creation). Import from ``kurosoden.tests.helpers``.
"""

from __future__ import annotations


async def _create_user(session, *, telegram_id: int = 12345, role: str = "user",
                        username: str = "testuser", first_name: str = "Test",
                        id_override: int | None = None, last_seen_at=None):
    from nekofetch.infrastructure.database.postgres.models import User
    from nekofetch.domain.enums import Role as RoleEnum
    u = User(telegram_id=telegram_id, username=username, first_name=first_name,
             role=RoleEnum(role), language="en")
    if id_override is not None:
        u.id = id_override
    if last_seen_at is not None:
        u.last_seen_at = last_seen_at
    session.add(u)
    await session.commit()
    return u


async def _create_request(session, *, code: str = "REQ-0001", user_id: int = 1,
                           anime_title: str = "Test Anime",
                           anime_doc_id: str = "anilist:12345",
                           source: str = "anikoto", status: str = "pending"):
    # Ensure the referenced user exists (FK constraint on user_id).
    from sqlalchemy import select
    from nekofetch.infrastructure.database.postgres.models import Request, User
    from nekofetch.domain.enums import RequestStatus
    existing = (await session.execute(select(User.id).where(User.id == user_id))).first()
    if not existing:
        await _create_user(session, id_override=user_id, telegram_id=user_id + 10000)
    r = Request(code=code, user_id=user_id, anime_title=anime_title,
                anime_doc_id=anime_doc_id, source=source,
                scope="entire_series", status=RequestStatus(status))
    session.add(r)
    await session.commit()
    return r


async def _create_channel_post(session, *, anime_doc_id: str = "anilist:12345",
                                main_message_id: int = 55):
    from nekofetch.infrastructure.database.postgres.models import ChannelPost
    cp = ChannelPost(anime_doc_id=anime_doc_id, main_channel_id=-1001234567890,
                     main_message_id=main_message_id)
    session.add(cp)
    await session.commit()
    return cp


async def _create_distribution_bot(session, *, anime_doc_id: str = "anilist:12345",
                                    username: str = "testbot_axw", enabled: bool = True):
    from nekofetch.infrastructure.database.postgres.models import DistributionBot
    bot = DistributionBot(name="Test Bot", username=username,
                          anime_doc_id=anime_doc_id,
                          encrypted_token="fake-encrypted-token", enabled=enabled)
    session.add(bot)
    await session.commit()
    return bot


async def _create_admin_availability(session, *, admin_telegram_id: int = 100,
                                      admin_name: str = "Test Admin",
                                      is_available: bool = True,
                                      assigned_bots: list | None = None,
                                      scheduled_breaks: list | None = None,
                                      total_tasks_completed: int = 0,
                                      weight: int = 1,
                                      working_hours: dict | None = None,
                                      timezone: str | None = None,
                                      country: str | None = None,
                                      max_hours_per_day: int | None = None,
                                      slots_weekday: list | None = None,
                                      slots_weekend: list | None = None):
    from kurosoden.shared.admin_assignment import AdminAvailability
    if assigned_bots is None:
        assigned_bots = ["lelouch", "levi", "senku", "gojo"]
    a = AdminAvailability(admin_telegram_id=admin_telegram_id,
                          admin_name=admin_name, is_available=is_available,
                          assigned_bots=assigned_bots,
                          scheduled_breaks=scheduled_breaks or [],
                          total_tasks_completed=total_tasks_completed,
                          weight=weight,
                          working_hours=working_hours,
                          timezone=timezone,
                          country=country,
                          max_hours_per_day=max_hours_per_day,
                          slots_weekday=slots_weekday,
                          slots_weekend=slots_weekend)
    session.add(a)
    await session.commit()
    return a


async def _create_admin_assignment(session, *, admin_telegram_id: int = 100,
                                    request_code: str = "REQ-0001",
                                    stage: str = "levi", status: str = "assigned"):
    from kurosoden.shared.admin_assignment import AdminAssignment
    a = AdminAssignment(admin_telegram_id=admin_telegram_id,
                        request_code=request_code, stage=stage, status=status)
    session.add(a)
    await session.commit()
    return a
