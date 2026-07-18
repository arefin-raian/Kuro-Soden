"""Kuro Sōden · Userbot Session Manager — a friendly, interactive TUI for
adding / listing / removing the Telegram **user** accounts the pipeline logs in
with.

Why this exists
---------------
The pipeline needs *user* sessions (not bot tokens) to read other bots' history,
join private channels, and drive @acutebot-style automation. Those sessions must
be created once interactively (phone → code → optional 2FA), which produces a
portable ``session_string``. :class:`~nekofetch.sources.telegram.userbot.UserbotPool`
then loads them non-interactively at runtime from the ``TELEGRAM_USERBOT_ACCOUNTS``
line in ``.env`` (a single-line JSON array of ``{"name", "session_string"}``).

This script owns that whole out-of-band step so nobody has to hand-craft JSON or
paste session strings: run it, sign in, and it writes the account straight into
``.env`` (making a timestamped ``.env.bak`` first). Multiple accounts are the
whole point — the pool rotates across them on flood-wait / failure — so the tool
is a loop you can run as many times as you have accounts.

    python scripts/userbot_manager.py       # interactive menu
    (or double-click add_userbot.bat on Windows)

Account naming: we take the account's **name** (first name), slugified to a safe
identifier. If the name isn't plain text (non-Latin script, emoji) or is empty,
we fall back to the @username, and finally to an ordered ``account_N`` slot — so
every entry always has a clean, unique handle in the pool.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import types
from datetime import datetime
from pathlib import Path

# ── ``kurosoden`` namespace bootstrap (mirrors main.py / clear_database.py) ────
# scripts/ is one level under the repo root. Put the root on sys.path, chdir into
# it (so ``get_env()`` reads Kuro Sōden's ``.env``, not a parent NekoFetch one),
# and register the synthetic ``kurosoden`` namespace package.
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

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

ENV_PATH = _HERE / ".env"
ACCOUNTS_KEY = "TELEGRAM_USERBOT_ACCOUNTS"

console = Console()


# ── .env read / write ─────────────────────────────────────────────────────────

def _read_env_text() -> str:
    if not ENV_PATH.is_file():
        raise FileNotFoundError(
            f"No .env found at {ENV_PATH}. Copy .env.example to .env and fill in "
            "TELEGRAM_API_ID / TELEGRAM_API_HASH first."
        )
    return ENV_PATH.read_text(encoding="utf-8")


def load_accounts() -> list[dict]:
    """Parse the current ``TELEGRAM_USERBOT_ACCOUNTS`` JSON array (or []).

    The value is a single-line JSON array; the session strings may themselves
    contain ``=``, so we split the key on the *first* ``=`` only.
    """
    text = _read_env_text()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() != ACCOUNTS_KEY:
            continue
        value = value.strip()
        if not value:
            return []
        try:
            data = json.loads(value)
            return [a for a in data if isinstance(a, dict) and a.get("session_string")]
        except json.JSONDecodeError:
            console.print(
                f"[yellow]⚠ Existing {ACCOUNTS_KEY} isn't valid JSON — treating it "
                "as empty. Your old value is preserved in the .env.bak backup.[/]"
            )
            return []
    return []


def save_accounts(accounts: list[dict]) -> Path:
    """Write ``accounts`` back to the ``TELEGRAM_USERBOT_ACCOUNTS`` line, creating a
    timestamped ``.env.bak`` first and preserving every other line verbatim."""
    text = _read_env_text()
    newline = "\r\n" if "\r\n" in text else "\n"

    # Back up before touching anything.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ENV_PATH.with_name(f".env.bak-{stamp}")
    backup.write_text(text, encoding="utf-8")

    serialized = json.dumps(accounts, ensure_ascii=True, separators=(",", ":"))
    new_line = f"{ACCOUNTS_KEY}={serialized}"

    lines = text.split(newline)
    replaced = False
    for i, line in enumerate(lines):
        key = line.partition("=")[0].strip()
        if key == ACCOUNTS_KEY:
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        # Insert right after TELEGRAM_API_HASH if present, else at the top.
        idx = next((i + 1 for i, ln in enumerate(lines)
                    if ln.partition("=")[0].strip() == "TELEGRAM_API_HASH"), 0)
        lines.insert(idx, new_line)

    ENV_PATH.write_text(newline.join(lines), encoding="utf-8")
    return backup


# ── account naming ──────────────────────────────────────────────────────────────

def _slugify(value: str | None) -> str:
    """Lowercase ASCII ``[a-z0-9_]`` slug, or '' if nothing plain-text survives.

    Non-Latin names (e.g. レイ) and emoji collapse to '' → caller falls back."""
    if not value:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug


def derive_name(me, existing: set[str], index: int) -> str:
    """Pick a clean, unique handle for the pool.

    Priority: the account's **name** (first_name) → @username → ordered
    ``account_N`` slot. The result is made unique against ``existing``."""
    base = _slugify(getattr(me, "first_name", None)) \
        or _slugify(getattr(me, "username", None)) \
        or f"account_{index}"
    name, n = base, index
    while name in existing:
        n += 1
        name = f"{base}_{n}"
    return name


# ── login flow ────────────────────────────────────────────────────────────────

async def login_and_export(api_id: int, api_hash: str) -> tuple[str, object] | None:
    """Interactively sign a user account in and return ``(session_string, me)``.

    Uses an in-memory Pyrogram client so no ``.session`` file is left on disk —
    the portable session string is the only artifact, and it goes into .env."""
    from pyrogram import Client
    from pyrogram.errors import (
        BadRequest,
        FloodWait,
        PhoneCodeExpired,
        PhoneCodeInvalid,
        PhoneNumberInvalid,
        SessionPasswordNeeded,
    )

    phone = Prompt.ask("  [bold]Phone number[/] [dim](international, e.g. +14155550101)[/]")
    phone = phone.strip().replace(" ", "")
    if not phone:
        console.print("  [red]No phone number entered — cancelled.[/]")
        return None

    client = Client(
        name="kurosoden_userbot_gen",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True,
    )

    try:
        await client.connect()
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [red]Could not connect to Telegram: {exc}[/]")
        return None

    try:
        with console.status("  Sending login code…", spinner="dots"):
            sent = await client.send_code(phone)
        console.print("  [green]✓[/] Code sent. Check your Telegram app "
                      "([dim]not SMS unless Telegram falls back[/]).")

        # Code entry — allow re-entry on typos, resend on expiry.
        signed_in = False
        for attempt in range(4):
            code = Prompt.ask("  [bold]Login code[/]").strip().replace(" ", "")
            try:
                await client.sign_in(phone, sent.phone_code_hash, code)
                signed_in = True
                break
            except PhoneCodeInvalid:
                console.print("  [yellow]That code was wrong. Try again.[/]")
            except PhoneCodeExpired:
                console.print("  [yellow]That code expired — sending a fresh one.[/]")
                with console.status("  Resending code…", spinner="dots"):
                    sent = await client.send_code(phone)
            except SessionPasswordNeeded:
                signed_in = await _two_factor(client)
                break
        if not signed_in:
            console.print("  [red]Could not sign in. Cancelled.[/]")
            return None

        me = await client.get_me()
        session_string = await client.export_session_string()
        return session_string, me

    except PhoneNumberInvalid:
        console.print("  [red]That phone number was rejected by Telegram.[/]")
        return None
    except FloodWait as exc:
        console.print(f"  [red]Telegram asked us to wait {exc.value}s (flood-wait). "
                      "Try again later.[/]")
        return None
    except BadRequest as exc:
        console.print(f"  [red]Telegram rejected the request: {exc}[/]")
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


async def _two_factor(client) -> bool:
    """Handle the 2FA cloud-password step; True on success."""
    from pyrogram.errors import BadRequest, PasswordHashInvalid

    for _ in range(3):
        pw = Prompt.ask("  [bold]Two-step (2FA) password[/]", password=True)
        try:
            await client.check_password(pw)
            return True
        except PasswordHashInvalid:
            console.print("  [yellow]Wrong password. Try again.[/]")
        except BadRequest as exc:
            console.print(f"  [red]{exc}[/]")
            return False
    return False


# ── UI screens ────────────────────────────────────────────────────────────────

def _banner() -> Panel:
    title = Text("⚔  Kuro Sōden · Userbot Session Manager", style="bold cyan")
    sub = Text("Add, list, and remove the Telegram user accounts the pipeline "
               "rotates through.", style="dim")
    return Panel(Align.center(Text.assemble(title, "\n", sub)),
                 border_style="cyan", padding=(1, 2))


def render_accounts(accounts: list[dict]) -> None:
    if not accounts:
        console.print(Panel("[dim]No userbot accounts configured yet. "
                            "Choose [bold]A[/bold] to add your first one.[/]",
                            border_style="yellow", title="Accounts"))
        return
    table = Table(title="Configured userbot accounts", border_style="cyan",
                  header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name", style="green")
    table.add_column("Session (masked)", style="dim")
    for i, acc in enumerate(accounts, 1):
        s = acc.get("session_string", "")
        masked = f"{s[:8]}…{s[-6:]}" if len(s) > 20 else "…"
        table.add_row(str(i), acc.get("name", "?"), masked)
    console.print(table)


async def do_add(api_id: int, api_hash: str) -> None:
    console.rule("[bold]Add an account")
    accounts = load_accounts()
    existing = {a.get("name") for a in accounts}

    result = await login_and_export(api_id, api_hash)
    if not result:
        return
    session_string, me = result

    suggested = derive_name(me, existing, index=len(accounts) + 1)
    who = getattr(me, "first_name", None) or getattr(me, "username", None) or "account"
    uname = f" (@{me.username})" if getattr(me, "username", None) else ""
    console.print(f"  [green]✓ Signed in as[/] [bold]{who}{uname}[/] "
                  f"[dim](id {getattr(me, 'id', '?')})[/]")

    name = Prompt.ask("  [bold]Save this account as[/]", default=suggested).strip()
    name = _slugify(name) or suggested
    while name in existing:
        console.print(f"  [yellow]'{name}' is already used — pick another.[/]")
        name = _slugify(Prompt.ask("  [bold]Name[/]", default=f"{name}_2")) or f"{name}_2"

    accounts.append({"name": name, "session_string": session_string})
    backup = save_accounts(accounts)
    console.print(f"  [green]✓ Saved[/] as [bold]{name}[/] → {ENV_PATH.name} "
                  f"[dim](backup: {backup.name})[/]\n")


def do_remove() -> None:
    console.rule("[bold]Remove an account")
    accounts = load_accounts()
    if not accounts:
        console.print("  [dim]Nothing to remove.[/]\n")
        return
    render_accounts(accounts)
    raw = Prompt.ask("  [bold]Remove which #[/] [dim](blank to cancel)[/]", default="").strip()
    if not raw:
        return
    if not raw.isdigit() or not (1 <= int(raw) <= len(accounts)):
        console.print("  [red]Not a valid row number.[/]\n")
        return
    victim = accounts[int(raw) - 1]
    if not Confirm.ask(f"  Remove [bold]{victim.get('name')}[/]?", default=False):
        return
    accounts.pop(int(raw) - 1)
    backup = save_accounts(accounts)
    console.print(f"  [green]✓ Removed[/] [dim](backup: {backup.name})[/]\n")


async def main() -> None:
    console.print(_banner())

    try:
        from nekofetch.core.config import get_env
        env = get_env()
        api_id, api_hash = env.telegram_api_id, env.telegram_api_hash
    except Exception as exc:  # noqa: BLE001
        console.print(Panel(f"[red]Couldn't read TELEGRAM_API_ID / TELEGRAM_API_HASH "
                            f"from .env:[/]\n{exc}", border_style="red"))
        return

    console.print(f"  [dim]Target .env:[/] {ENV_PATH}")
    console.print(f"  [dim]API id:[/] {api_id}\n")

    while True:
        render_accounts(load_accounts())
        console.print(
            "\n  [bold]A[/]dd · [bold]L[/]ist (refresh) · "
            "[bold]R[/]emove · [bold]Q[/]uit"
        )
        choice = Prompt.ask(
            "  [bold]Action[/]",
            choices=["a", "l", "r", "q"],
            default="a",
        ).lower()
        console.print()
        if choice == "a":
            try:
                await do_add(api_id, api_hash)
            except KeyboardInterrupt:
                console.print("\n  [dim]cancelled[/]\n")
        elif choice == "l":
            continue  # loop re-renders the table
        elif choice == "r":
            do_remove()
        elif choice == "q":
            console.print("  [cyan]Done. The pool will pick these up on next start.[/]")
            return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
