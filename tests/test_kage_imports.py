"""Smoke tests — verify all Kage modules import without errors.

These tests ensure the kage/ package is properly structured and all
import paths resolve correctly. No actual bot connections needed.
"""

import sys
from pathlib import Path

# Standalone: kage/ IS the project root with nekofetch vendored inside.
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))


def test_kage_package_imports():
    """kage/__init__.py should be importable."""
    import kage
    assert kage.__version__ == "0.1.0"


def test_shared_imports():
    """All shared modules should import cleanly."""
    from kage.shared.pipeline_manager import PipelineManager
    from kage.shared.admin_assignment import AdminAssignmentEngine
    from kage.shared.admin_assignment import AdminAssignment, AdminAvailability
    from kage.shared.dedup import DedupService, DedupResult
    from kage.shared.models import AdminAssignment, AdminAvailability

    assert PipelineManager is not None
    assert AdminAssignmentEngine is not None
    assert DedupService is not None
    assert DedupResult is not None


def test_bot_app_imports():
    """All bot app.py modules should be importable."""
    from kage.bots.lelouch.app import build_lelouch
    from kage.bots.levi.app import build_levi
    from kage.bots.senku.app import build_senku
    from kage.bots.gojo.app import build_gojo

    assert build_lelouch is not None
    assert build_levi is not None
    assert build_senku is not None
    assert build_gojo is not None


def test_bot_handler_imports():
    """All bot handler modules should be importable."""
    from kage.bots.lelouch.handlers import register_all as lelouch_register
    from kage.bots.levi.handlers import register_all as levi_register
    from kage.bots.senku.handlers import register_all as senku_register
    from kage.bots.gojo.handlers import register_all as gojo_register

    assert lelouch_register is not None
    assert levi_register is not None
    assert senku_register is not None
    assert gojo_register is not None


def test_dedup_result_defaults():
    """DedupResult defaults should be correct."""
    from kage.shared.dedup import DedupResult

    r = DedupResult()
    assert r.exists is False
    assert r.source == ""
    assert r.bot_username is None
    assert r.request_code is None

    r2 = DedupResult(exists=True, source="main_channel", title="Test")
    assert r2.exists is True
    assert r2.source == "main_channel"


def test_admin_assignment_result_defaults():
    """AssignmentResult should hold correct admin info."""
    from kage.shared.admin_assignment import AssignmentResult

    r = AssignmentResult(
        admin_telegram_id=12345,
        admin_name="Test Admin",
        tasks_active=2,
        tasks_completed=10,
    )
    assert r.admin_telegram_id == 12345
    assert r.admin_name == "Test Admin"
    assert r.tasks_active == 2
    assert r.tasks_completed == 10
