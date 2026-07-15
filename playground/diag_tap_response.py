"""Throwaway diagnostic — tap the first acutebot menu candidate and dump
chat-history + CallbackQueryAnswer shape so we can see which pattern
(a/b/c) @acutebot actually uses to deliver the info card.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from nekofetch.sources.telegram.userbot import UserbotPool

_BOT_USERNAME = "acutebot"


async def _diag(client) -> None:
    await client.send_message(_BOT_USERNAME, "/anime Attack on Titan")
    await asyncio.sleep(2.5)

    # Pattern (a) is the edit-in-place case; without inspecting markup we
    # don't yet know which (title-button) row to tap — guess the first row.
    hist_before = []
    async for m in client.get_chat_history(_BOT_USERNAME, limit=20):
        hist_before.append(m)
    if not hist_before:
        print("❌ NO MESSAGES from @acutebot — bot didn't respond.")
        return
    menu_msg = hist_before[0]

    kb = getattr(
        getattr(menu_msg, "reply_markup", None), "inline_keyboard", None
    )
    cb_data = None
    btn_text = None
    if kb and kb[0]:
        cb_data = kb[0][0].callback_data
        btn_text = (kb[0][0].text or "").strip()

    print("=== HISTORY BEFORE TAP ===")
    for m in hist_before[:3]:
        snippet = (m.text or m.caption or "")[:60].replace("\n", " ")
        print(f"  [{m.id}] {snippet}")

    if not cb_data:
        print("❌ first row has no callback_data — not a title-button menu.")
        return

    print(f"\n=== TAPPING first row: {btn_text!r} cb={cb_data!r} ===")
    try:
        ans = await client.request_callback_answer(
            menu_msg.chat.id,
            menu_msg.id,
            cb_data,
            timeout=8,
        )
        print("✅ request_callback_answer returned")
        print(f"  answer.text:    {getattr(ans, 'text', None)!r}")
        print(f"  answer.url:     {getattr(ans, 'url', None)!r}")
        am = getattr(ans, "message", None)
        print(
            f"  answer.message: "
            f"{type(am).__name__ if am else None}"
        )
        if am is not None:
            if isinstance(am, str):
                snippet = am.replace("\n", " ")[:100]
                print(f"     [alert_text] {snippet!r}")
            else:
                snippet = (am.text or am.caption or "")[:100].replace("\n", " ")
                print(f"     [{am.id}] {snippet}")
    except Exception as exc:
        print(f"❌ request_callback_answer raised: {exc!r}")
        return

    await asyncio.sleep(3)
    hist_after = []
    async for m in client.get_chat_history(_BOT_USERNAME, limit=20):
        hist_after.append(m)
    print("\n=== HISTORY AFTER TAP ===")
    for m in hist_after[:5]:
        snippet = (m.text or m.caption or "")[:60].replace("\n", " ")
        print(f"  [{m.id}] {snippet}")
    # Compare to confirm new message arrived vs nothing changed.
    new_ids = [m.id for m in hist_after if m.id not in {x.id for x in hist_before}]
    print(f"\nNEW messages after tap (id > {menu_msg.id}): {new_ids}")


async def main() -> None:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_path = os.environ.get("SESSION_PATH", r"C:\data\sessions")
    pool = UserbotPool.from_env(api_id, api_hash, session_path)
    try:
        await pool.execute(_diag)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
