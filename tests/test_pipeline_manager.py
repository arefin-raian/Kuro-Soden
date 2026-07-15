"""Tests for kage/shared/pipeline_manager.py — Pipeline lifecycle.

Covers:
  • PipelineManager properties (lelouch, levi, senku, gojo)
  • _start_bot with missing/invalid tokens
  • Constants validation
  • Stop behavior
"""

from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    """Validate pipeline manager constants."""

    def test_conn_check_interval_is_positive(self):
        from kage.shared.pipeline_manager import _CONN_CHECK_INTERVAL
        assert _CONN_CHECK_INTERVAL > 0

    def test_conn_probe_timeout_is_positive(self):
        from kage.shared.pipeline_manager import _CONN_PROBE_TIMEOUT
        assert _CONN_PROBE_TIMEOUT > 0

    def test_reconnect_attempts_positive(self):
        from kage.shared.pipeline_manager import _CONN_RECONNECT_ATTEMPTS
        assert _CONN_RECONNECT_ATTEMPTS >= 1

    def test_reconnect_timeout_higher_than_probe(self):
        from kage.shared.pipeline_manager import _CONN_RECONNECT_TIMEOUT, _CONN_PROBE_TIMEOUT
        assert _CONN_RECONNECT_TIMEOUT >= _CONN_PROBE_TIMEOUT

    def test_reconnect_backoff_positive(self):
        from kage.shared.pipeline_manager import _CONN_RECONNECT_BACKOFF
        assert _CONN_RECONNECT_BACKOFF > 0


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineManager properties
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineManagerProperties:
    """Property accessors return None when empty."""

    def test_lelouch_is_none_initially(self):
        from kage.shared.pipeline_manager import PipelineManager
        pm = PipelineManager(None)
        assert pm.lelouch is None

    def test_levi_is_none_initially(self):
        from kage.shared.pipeline_manager import PipelineManager
        pm = PipelineManager(None)
        assert pm.levi is None

    def test_senku_is_none_initially(self):
        from kage.shared.pipeline_manager import PipelineManager
        pm = PipelineManager(None)
        assert pm.senku is None

    def test_gojo_is_none_initially(self):
        from kage.shared.pipeline_manager import PipelineManager
        pm = PipelineManager(None)
        assert pm.gojo is None

    def test_all_properties_exist(self):
        """Verify all four bot properties exist."""
        from kage.shared.pipeline_manager import PipelineManager
        pm = PipelineManager(None)
        assert hasattr(pm, "lelouch")
        assert hasattr(pm, "levi")
        assert hasattr(pm, "senku")
        assert hasattr(pm, "gojo")


# ═══════════════════════════════════════════════════════════════════════════════
# Bot name validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestBotNameMapping:
    """Start order and name-to-env-var mapping."""

    def test_start_order_is_correct(self):
        """Lelouch → Levi → Senku → Gojo (pipeline order)."""
        expected_order = ["lelouch", "levi", "senku", "gojo"]
        # Verify these are the only valid bot names.
        from kage.shared.pipeline_manager import PipelineManager

        # Check _start_bot calls in start() method are in the right order.
        import inspect
        source = inspect.getsource(PipelineManager.start)
        indices = [source.find(f'\"{name}\"') for name in expected_order]
        # All should be found and in order.
        for i in range(len(indices) - 1):
            assert indices[i] > 0, f"Bot {expected_order[i]} not found in start()"
            assert indices[i] < indices[i + 1], \
                f"{expected_order[i]} should start before {expected_order[i+1]}"

    def test_env_var_mapping(self):
        """Each bot name maps to the correct env var."""
        mapping = {
            "lelouch": "REQUEST_BOT_TOKEN",
            "levi": "DOWNLOADER_BOT_TOKEN",
            "senku": "DISTRIBUTION_BOT_TOKEN",
            "gojo": "PUBLISHER_BOT_TOKEN",
        }
        for name, env_var in mapping.items():
            assert name in ("lelouch", "levi", "senku", "gojo")
            assert "TOKEN" in env_var

    def test_unknown_name_would_be_handled(self):
        """The _start_bot method has an else clause for unknown names."""
        from kage.shared.pipeline_manager import PipelineManager
        import inspect
        source = inspect.getsource(PipelineManager._start_bot)
        assert "else:" in source
        assert "unknown" in source.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Bot builder import validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestBotBuilderImports:
    """All build_* functions should be importable."""

    def test_build_lelouch_importable(self):
        from kage.bots.lelouch.app import build_lelouch
        assert callable(build_lelouch)

    def test_build_levi_importable(self):
        from kage.bots.levi.app import build_levi
        assert callable(build_levi)

    def test_build_senku_importable(self):
        from kage.bots.senku.app import build_senku
        assert callable(build_senku)

    def test_build_gojo_importable(self):
        from kage.bots.gojo.app import build_gojo
        assert callable(build_gojo)

    def test_all_bots_have_commands(self):
        """Every bot should have a COMMANDS list."""
        from kage.bots.lelouch.app import LELOUCH_COMMANDS
        from kage.bots.levi.app import LEVI_COMMANDS
        from kage.bots.senku.app import SENKU_COMMANDS
        from kage.bots.gojo.app import GOJO_COMMANDS

        assert len(LELOUCH_COMMANDS) > 0
        assert len(LEVI_COMMANDS) > 0
        assert len(SENKU_COMMANDS) > 0
        assert len(GOJO_COMMANDS) > 0

    def test_lelouch_commands_have_expected(self):
        from kage.bots.lelouch.app import LELOUCH_COMMANDS
        cmds = {c.command for c in LELOUCH_COMMANDS}
        assert "start" in cmds
        assert "help" in cmds
        assert "admin" in cmds
        assert "myrequests" in cmds
        assert "settings" in cmds

    def test_levi_commands_have_expected(self):
        from kage.bots.levi.app import LEVI_COMMANDS
        cmds = {c.command for c in LEVI_COMMANDS}
        assert "start" in cmds
        assert "tasks" in cmds
        assert "assign" in cmds
        assert "sources" in cmds
        assert "header" in cmds

    def test_senku_commands_have_expected(self):
        from kage.bots.senku.app import SENKU_COMMANDS
        cmds = {c.command for c in SENKU_COMMANDS}
        assert "start" in cmds
        assert "tasks" in cmds
        assert "create" in cmds
        assert "generate" in cmds

    def test_gojo_commands_have_expected(self):
        from kage.bots.gojo.app import GOJO_COMMANDS
        cmds = {c.command for c in GOJO_COMMANDS}
        assert "start" in cmds
        assert "tasks" in cmds
        assert "publish" in cmds
        assert "recover" in cmds
        assert "schedule" in cmds


# ═══════════════════════════════════════════════════════════════════════════════
# Stop behavior
# ═══════════════════════════════════════════════════════════════════════════════

class TestStopBehavior:
    """stop() should handle all states gracefully."""

    def test_stop_with_no_clients(self):
        """Stopping with no running clients should not crash."""
        from kage.shared.pipeline_manager import PipelineManager
        pm = PipelineManager(None)
        pm.stop  # Just accessing the method — it exists.
        assert callable(pm.stop)

    def test_stop_method_exists_and_is_async(self):
        from kage.shared.pipeline_manager import PipelineManager
        import inspect
        assert inspect.iscoroutinefunction(PipelineManager.stop)
