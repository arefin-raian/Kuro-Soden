"""Tests for scripts/userbot_manager.py — the interactive tool that signs
Telegram user accounts in and writes their session strings into ``.env``.

The login flow is interactive (phone/code/2FA) and can't be unit-tested without
a live Telegram connection, so these tests cover the parts that touch the
filesystem and would corrupt real secrets if they regressed:

  • account naming / slugify fallbacks (name → username → account_N, uniqueness),
  • the ``.env`` round-trip (load → save → reload) preserving every other line,
  • the timestamped backup written before each save,
  • the malformed-JSON safety net (never nukes an unparseable value silently),
  • the first-``=``-only split (session strings legitimately contain ``=``).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "userbot_manager.py"


@pytest.fixture(scope="module")
def ubm():
    """Load the script as a module (it isn't importable via the package path)."""
    spec = importlib.util.spec_from_file_location("userbot_manager", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def env_file(tmp_path, ubm, monkeypatch):
    """A throwaway .env with API creds + one existing account; ENV_PATH points here."""
    path = tmp_path / ".env"
    path.write_text(
        "TELEGRAM_API_ID=12345\n"
        "TELEGRAM_API_HASH=deadbeefcafe\n"
        'TELEGRAM_USERBOT_ACCOUNTS=[{"name":"rai_yan_00","session_string":"AAAA=BB=="}]\n'
        "REDIS_URL=redis://localhost\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ubm, "ENV_PATH", path)
    return path


class _Me:
    def __init__(self, first_name=None, username=None, id=1):
        self.first_name = first_name
        self.username = username
        self.id = id


# ── slugify ───────────────────────────────────────────────────────────────────

class TestSlugify:
    def test_plain_name_lowercased_and_underscored(self, ubm):
        assert ubm._slugify("Levi Ackerman") == "levi_ackerman"

    def test_existing_slug_is_stable(self, ubm):
        assert ubm._slugify("rai_yan_00") == "rai_yan_00"

    def test_non_latin_collapses_to_empty(self, ubm):
        assert ubm._slugify("レイ") == ""

    def test_emoji_collapses_to_empty(self, ubm):
        assert ubm._slugify("🐱🐾") == ""

    def test_none_and_empty(self, ubm):
        assert ubm._slugify(None) == ""
        assert ubm._slugify("") == ""

    def test_strips_leading_trailing_separators(self, ubm):
        assert ubm._slugify("  --Cool_User!!  ") == "cool_user"


# ── derive_name ─────────────────────────────────────────────────────────────────

class TestDeriveName:
    def test_prefers_first_name(self, ubm):
        assert ubm.derive_name(_Me("Rai"), set(), 1) == "rai"

    def test_falls_back_to_username_when_name_non_latin(self, ubm):
        assert ubm.derive_name(_Me("レイ", "Cool_User"), set(), 1) == "cool_user"

    def test_falls_back_to_ordered_slot_when_nothing_plain_text(self, ubm):
        assert ubm.derive_name(_Me("レイ", None), {"account_1"}, 3) == "account_3"

    def test_uniquifies_against_existing(self, ubm):
        assert ubm.derive_name(_Me("Rai"), {"rai"}, 1) == "rai_2"

    def test_uniquify_skips_multiple_collisions(self, ubm):
        assert ubm.derive_name(_Me("Rai"), {"rai", "rai_2"}, 1) == "rai_3"


# ── load_accounts ───────────────────────────────────────────────────────────────

class TestLoadAccounts:
    def test_loads_existing(self, ubm, env_file):
        accounts = ubm.load_accounts()
        assert [a["name"] for a in accounts] == ["rai_yan_00"]
        # session string with '=' survives the first-'='-only split
        assert accounts[0]["session_string"] == "AAAA=BB=="

    def test_empty_value_returns_empty_list(self, ubm, env_file):
        env_file.write_text("TELEGRAM_USERBOT_ACCOUNTS=\n", encoding="utf-8")
        assert ubm.load_accounts() == []

    def test_missing_key_returns_empty_list(self, ubm, env_file):
        env_file.write_text("TELEGRAM_API_ID=1\n", encoding="utf-8")
        assert ubm.load_accounts() == []

    def test_malformed_json_returns_empty_not_crash(self, ubm, env_file):
        env_file.write_text("TELEGRAM_USERBOT_ACCOUNTS=[not json\n", encoding="utf-8")
        assert ubm.load_accounts() == []

    def test_drops_entries_without_session(self, ubm, env_file):
        env_file.write_text(
            'TELEGRAM_USERBOT_ACCOUNTS=[{"name":"a"},{"name":"b","session_string":"x"}]\n',
            encoding="utf-8",
        )
        assert [a["name"] for a in ubm.load_accounts()] == ["b"]

    def test_commented_line_ignored(self, ubm, env_file):
        env_file.write_text(
            '# TELEGRAM_USERBOT_ACCOUNTS=[{"name":"ghost","session_string":"z"}]\n',
            encoding="utf-8",
        )
        assert ubm.load_accounts() == []


# ── save_accounts ───────────────────────────────────────────────────────────────

class TestSaveAccounts:
    def test_round_trip_appends_and_reloads(self, ubm, env_file):
        accounts = ubm.load_accounts()
        accounts.append({"name": "account_2", "session_string": "SESS=WITH=EQ=="})
        ubm.save_accounts(accounts)

        reloaded = ubm.load_accounts()
        assert [a["name"] for a in reloaded] == ["rai_yan_00", "account_2"]
        assert reloaded[1]["session_string"] == "SESS=WITH=EQ=="

    def test_preserves_other_lines(self, ubm, env_file):
        before = env_file.read_text(encoding="utf-8").splitlines()
        ubm.save_accounts(ubm.load_accounts())
        after = env_file.read_text(encoding="utf-8").splitlines()
        assert len(after) == len(before)
        assert "TELEGRAM_API_HASH=deadbeefcafe" in after
        assert "REDIS_URL=redis://localhost" in after

    def test_exactly_one_accounts_line(self, ubm, env_file):
        ubm.save_accounts([{"name": "x", "session_string": "y"}])
        lines = env_file.read_text(encoding="utf-8").splitlines()
        hits = [l for l in lines if l.startswith("TELEGRAM_USERBOT_ACCOUNTS=")]
        assert len(hits) == 1
        # serialized compactly as a JSON array
        assert json.loads(hits[0].partition("=")[2]) == [{"name": "x", "session_string": "y"}]

    def test_creates_timestamped_backup(self, ubm, env_file):
        original = env_file.read_text(encoding="utf-8")
        backup = ubm.save_accounts(ubm.load_accounts())
        assert backup.exists()
        assert backup.name.startswith(".env.bak-")
        # backup holds the PRE-write content
        assert backup.read_text(encoding="utf-8") == original

    def test_inserts_after_api_hash_when_key_absent(self, ubm, env_file):
        env_file.write_text(
            "TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=abc\nREDIS_URL=r\n", encoding="utf-8"
        )
        ubm.save_accounts([{"name": "n", "session_string": "s"}])
        lines = env_file.read_text(encoding="utf-8").splitlines()
        hash_idx = next(i for i, l in enumerate(lines) if l.startswith("TELEGRAM_API_HASH="))
        acc_idx = next(i for i, l in enumerate(lines) if l.startswith("TELEGRAM_USERBOT_ACCOUNTS="))
        assert acc_idx == hash_idx + 1

    def test_missing_env_raises(self, ubm, tmp_path, monkeypatch):
        monkeypatch.setattr(ubm, "ENV_PATH", tmp_path / "nope.env")
        with pytest.raises(FileNotFoundError):
            ubm.load_accounts()
