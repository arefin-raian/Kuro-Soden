"""Kage ORM models — registered on NekoFetch's shared ``Base.metadata``.

Import this module at startup (Container.startup or migration env.py) so the
tables ``admin_assignments`` and ``admin_availability`` are materialised by
``Base.metadata.create_all()`` and picked up by Alembic autogenerate.
"""

# Re-export so `from kage.shared.models import AdminAssignment, AdminAvailability` works.
from kage.shared.admin_assignment import AdminAssignment, AdminAvailability  # noqa: F401

__all__ = ["AdminAssignment", "AdminAvailability"]
