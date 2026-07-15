"""Gojo — Publisher Bot (最強の術師 · The Strongest Sorcerer).

Handles:
  • Main channel post generation.
  • Franchise thumbnail generation.
  • TMDB synopsis (not AniList) for descriptions.
  • Caption template → admin review → Markdown/HTML edit.
  • Publish (immediate or scheduled).
  • Index update.
  • Channel recovery tools (banned → replace → update all buttons).

Reuses NekoFetch's PublishingService, MainChannelService, IndexChannelService.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from kage.shared.ui_helpers import reply_with_screen
from nekofetch.ui.artwork import pick_artwork

GOJO_COMMANDS = [
    BotCommand("start", "View your assigned publishing tasks"),
    BotCommand("tasks", "List active publishing tasks"),
    BotCommand("publish", "Review and publish: /publish REQ-XXXX"),
    BotCommand("recover", "Recover a banned channel: /recover REQ-XXXX"),
    BotCommand("schedule", "Schedule a post for later"),
    BotCommand("settings", "Configure the publisher bot"),
    BotCommand("help", "How publishing works"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(GOJO_COMMANDS)


def build_gojo(container: Container, token: str) -> Client:
    """Build and wire the Gojo (Publisher) bot client.

    All publish/recover/schedule handlers are registered via ``register_all``.
    """
    client = Client(
        name="kage-gojo",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    from kage.bots.gojo.handlers import register_all
    register_all(client, container)

    # ── Catch-all menu callback ─────────────────────────────────────────────
    # Inline buttons on /start route to `gojo|<action>`. The dispatcher below
    # maps every action to a real screen — no more "Type /X in chat" toasts.
    from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                                InlineKeyboardMarkup)
    from kage.shared.menu_router import settings_hub, settings_onboarding, tool_screen
    from kage.shared.settings_content import ALL_BY_BOT
    from nekofetch.ui.components import cb
    from nekofetch.ui.screens import Screen, send_screen

    @client.on_callback_query(filters.regex(r"^gojo\|"))
    async def _gojo_menu_fallback(client: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        parts = q.data.split("|", 2)
        action = parts[1] if len(parts) > 1 else "home"
        arg = parts[2] if len(parts) > 2 else ""
        bot = "gojo"

        # ¬¬ Home ¬¬
        if action == "home":
            caption = (
                "<b>🔮 Gojo Satoru — Publisher</b>\n\n"
                "<i>\"Throughout heaven and earth, I alone am the honored one.\"</i>\n\n"
                "I handle the final step:\n"
                "• Generate main channel posts\n"
                "• Create franchise thumbnails\n"
                "• Review and edit captions\n"
                "• Publish or schedule\n"
                "• Update the index\n"
                "• Recover banned channels"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Tasks", callback_data=cb(bot, "tasks")),
                 InlineKeyboardButton("🔮 Publish", callback_data=cb(bot, "publish"))],
                [InlineKeyboardButton("📅 Schedule", callback_data=cb(bot, "schedule")),
                 InlineKeyboardButton("🛡 Recover", callback_data=cb(bot, "recover"))],
                [InlineKeyboardButton("⚙️ Settings", callback_data=cb(bot, "settings"))],
            ])
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Tool panels ¬¬
        if action in ("tasks", "publish", "recover", "schedule"):
            titles = {"tasks": "📋 Your Publishing Tasks",
                      "publish": "🔮 Publish Review",
                      "recover": "🛡 Channel Recovery",
                      "schedule": "📅 Schedule Publication"}
            body_map = {
                "tasks": [
                    "<b>/tasks</b> — what is waiting on you to publish.",
                    "<b>What you see here:</b>",
                    "  🔹 <b>Code</b>  ·  <b>Anime</b>  ·  <b>Stage</b>",
                    "<blockquote>Distribution finishes before this stage, so everything here has a content pack ready.</blockquote>",
                    "💡 <b>Example:</b> Tap <b>📋 Tasks</b> — no command needed.",
                ],
                "publish": [
                    "<b>/publish REQ-XXXX</b> — reviews and publishes.",
                    "<b>Steps:</b>",
                    "  1. Tap <b>🔮 Publish</b> here",
                    "  2. Send <code>/publish REQ-XXXX</code>",
                    "  3. Review the caption (Markdown/HTML)",
                    "  4. Tap <b>🚀 Publish Now</b> or <b>✏️ Edit</b>",
                    "<blockquote>The publisher commits to the main channel and updates the index. You can edit until you publish.</blockquote>",
                    "💡 <b>Example:</b> <code>/publish REQ-12AB</code>",
                ],
                "recover": [
                    "<b>/recover REQ-XXXX</b> — recovers a banned channel.",
                    "<b>What it does:</b>",
                    "  🔹 Detects the banned distribution channel",
                    "  🔹 Recreates a replacement under the bot factory",
                    "  🔹 Updates <b>every</b> button in main + index channels",
                    "<blockquote>Recovery is automatic — you don't need to rebuild the channel yourself.</blockquote>",
                    "💡 <b>Example:</b> <code>/recover REQ-12AB</code>",
                ],
                "schedule": [
                    "<b>/schedule REQ-XXXX YYYY-MM-DD HH:MM</b>",
                    "<b>Steps:</b>",
                    "  1. Pick a task and a time (UTC)",
                    "  2. Send the schedule command",
                    "  3. The publisher takes over at the target time",
                    "<blockquote>Scheduling is opt-in — leave it off for publishing immediately.</blockquote>",
                    "💡 <b>Example:</b> <code>/schedule REQ-12AB 2026-08-01 18:00</code>",
                ],
            }
            caption, keyboard = tool_screen(
                bot, title=titles[action],
                kicker="Tap a button from /start — no typing needed.",
                lines=body_map[action],
                back="home",
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Settings hub ¬¬
        if action == "settings":
            caption, keyboard = settings_hub(
                bot, title="Gojo Settings",
                body=("Configure the caption template, main-channel routing, "
                      "and A-Z index handling.\n\n"
                      "<i>Tap a row to open the help panel for that key, then "
                      "send the new value as a chat message.</i>"),
                items=[("Caption Template", "caption"),
                       ("Main Channel", "main"),
                       ("Index Settings", "index")],
            )
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ set|<key> onboarding ¬¬
        if action == "set" and arg:
            info = ALL_BY_BOT.get(bot, {}).get(arg)
            if info:
                caption, keyboard = settings_onboarding(
                    bot, arg, title=info["title"], about=info["about"],
                    when_to_use=info.get("when_to_use", ""),
                    options=info.get("options"),
                    placeholders=info.get("placeholders"),
                    supports_html=info.get("supports_html", False),
                    example=info.get("example", ""),
                    danger=info.get("danger", ""),
                    hint=info.get("hint", "Send the new value as a chat message."),
                )
                await send_screen(client, q.message.chat.id,
                                  Screen(caption=caption, image=pick_artwork(bot),
                                         keyboard=keyboard), old_msg=q.message)
                await q.answer()
                return

        await q.answer(f"Action “{action}” not wired yet.", show_alert=True)

    # ── /start ────────────────────────────────────────────────────────────────
    # Rich UI: sticker → loading animation → welcome screen with inline keyboard
    # and Gojo-themed artwork (images/gojo/).
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen
        from nekofetch.ui.components import cb, keyboard
        from nekofetch.ui.artwork import pick_artwork
        from kage.shared.ui_helpers import send_rich_welcome

        rows = [
            [("📋 Tasks", cb("gojo", "tasks")),
             ("🔮 Publish", cb("gojo", "publish"))],
            [("📅 Schedule", cb("gojo", "schedule")),
             ("🛡 Recover", cb("gojo", "recover"))],
            [("⚙️ Settings", cb("gojo", "settings")),
             ("❓ Help", cb("misc", "help"))],
        ]
        screen = Screen(
            caption=(
                "<b>🔮 Gojo Satoru — Publisher</b>\n\n"
                "<i>\"Throughout heaven and earth, I alone am the honored one.\"</i>\n\n"
                "I handle the final step:\n"
                "• Generate main channel posts\n"
                "• Create franchise thumbnails\n"
                "• Review and edit captions\n"
                "• Publish or schedule\n"
                "• Update the index\n"
                "• Recover banned channels"
            ),
            image=pick_artwork("gojo"),
            keyboard=keyboard(*rows),
        )
        await send_rich_welcome(client, container, message, screen)

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen
        from nekofetch.ui.components import cb, keyboard

        screen = Screen(
            caption="<b>⚙️ Gojo Settings</b>\n\n"
                     "Configure publishing preferences and caption templates.",
            keyboard=keyboard(
                [("Caption Template", cb("gojo", "set", "caption")),
                 ("Main Channel", cb("gojo", "set", "main")),
                 ("Index Settings", cb("gojo", "set", "index"))],
                [("Back", cb("gojo", "home"))],
            ),
            image=pick_artwork("gojo"),
        )
        await send_screen(client, message.chat.id, screen)

    return client
