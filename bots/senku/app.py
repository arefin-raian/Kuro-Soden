"""Senku — Distribution Bot (科学の使者 · The Science Messenger).

Handles:
  • Channel creation guidance for admins.
  • TMDB poster → profile picture prompt.
  • Auto-generate: info card, stickers, season separators, watch guide, footer.
  • Season thumbnail generation (posters, logos, layouts).
  • Per-bot settings panel.

Reuses NekoFetch's BotContentService + BotFactory for all content generation.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import BotCommand, Message

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from kurosoden.shared.ui_helpers import reply_with_screen
from nekofetch.ui.artwork import pick_artwork

SENKU_COMMANDS = [
    BotCommand("start", "View your assigned distribution tasks"),
    BotCommand("tasks", "List active distribution tasks"),
    BotCommand("create", "Create a new distribution channel"),
    BotCommand("generate", "Generate content: /generate REQ-XXXX"),
    BotCommand("settings", "Configure the distribution bot"),
    BotCommand("help", "How distribution works"),
]

log = get_logger(__name__)


async def publish_commands(client: Client) -> None:
    await client.set_bot_commands(SENKU_COMMANDS)


def build_senku(container: Container, token: str) -> Client:
    """Build and wire the Senku (Distribution) bot client.

    All task/generate/create handlers are registered via ``register_all``.
    """
    client = Client(
        name="kurosoden-senku",
        api_id=container.env.telegram_api_id,
        api_hash=container.env.telegram_api_hash,
        bot_token=token,
        workdir=str(container.env.session_path),
    )
    client.container = container

    from kurosoden.bots.senku.handlers import register_all
    register_all(client, container)

    # ── Catch-all menu callback ─────────────────────────────────────────────
    # Inline buttons on /start route to `senku|<action>`. The dispatcher below
    # maps every action to a real screen — no more "Type /X in chat" toasts.
    from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                                InlineKeyboardMarkup)
    from kurosoden.shared.menu_router import settings_hub, settings_onboarding, tool_screen
    from kurosoden.shared.settings_content import ALL_BY_BOT
    from nekofetch.ui.components import cb
    from nekofetch.ui.screens import Screen, send_screen

    @client.on_callback_query(filters.regex(r"^senku\|"))
    async def _senku_menu_fallback(client: Client, q: CallbackQuery) -> None:
        if q.message is None:
            await q.answer()
            return
        parts = q.data.split("|", 2)
        action = parts[1] if len(parts) > 1 else "home"
        arg = parts[2] if len(parts) > 2 else ""
        bot = "senku"

        # ¬¬ Home ¬¬
        if action == "home":
            caption = (
                "<b>🧪 Senku Ishigami — Distribution</b>\n\n"
                "<i>\"Ten billion percent — this channel will be perfect.\"</i>\n\n"
                "I handle distribution:\n"
                "• Guide channel creation\n"
                "• Generate info cards & stickers\n"
                "• Create season separators & watch guides\n"
                "• Add footers and branding"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Tasks", callback_data=cb(bot, "tasks")),
                 InlineKeyboardButton("🧪 Generate", callback_data=cb(bot, "generate"))],
                [InlineKeyboardButton("📢 Create Channel", callback_data=cb(bot, "create"))],
                [InlineKeyboardButton("⚙️ Settings", callback_data=cb(bot, "settings"))],
            ])
            await send_screen(client, q.message.chat.id,
                              Screen(caption=caption, image=pick_artwork(bot),
                                     keyboard=keyboard), old_msg=q.message)
            await q.answer()
            return

        # ¬¬ Tool panels ¬¬
        if action in ("tasks", "create", "generate"):
            titles = {"tasks": "📋 Your Distribution Tasks",
                      "create": "📢 Create a Channel",
                      "generate": "🧪 Generate Channel Content"}
            body_map = {
                "tasks": [
                    "<b>/tasks</b> — line up everything waiting on you.",
                    "<b>What you see here:</b>",
                    "  🔹 <b>Code</b>  ·  <b>Anime</b>  ·  <b>Stage</b>",
                    "<blockquote>Each card links to the per-title content you need to generate.</blockquote>",
                    "💡 <b>Example:</b> Tap <b>📋 Tasks</b> — no command needed.",
                ],
                "create": [
                    "<b>/create REQ-XXXX</b> — creates the distribution channel.",
                    "<b>Steps:</b>",
                    "  1. Confirm the franchise with <code>/confirm</code>",
                    "  2. Bot creates the channel + profile picture",
                    "  3. You generate the content pack",
                    "<blockquote>The channel name follows your branding template — override per-title if needed.</blockquote>",
                    "💡 <b>Example:</b> <code>/create REQ-12AB</code>",
                ],
                "generate": [
                    "<b>/generate REQ-XXXX</b> — runs the content pack.",
                    "<b>What it generates:</b>",
                    "  🔹 Info card  🔹 Season separators  🔹 Watch guide",
                    "  🔹 Footer  🔹 Stickers",
                    "<blockquote>Each artifact is editable — review and approve before the publisher locks it.</blockquote>",
                    "💡 <b>Example:</b> <code>/generate REQ-12AB</code>",
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
                bot, title="Senku Settings",
                body=("Configure channel branding, footer text, sticker packs, "
                      "and the layout of every auto-generated artifact.\n\n"
                      "<i>Tap a row to open the help panel for that key, then "
                      "send the new value as a chat message.</i>"),
                items=[("Branding", "branding"), ("Content Layout", "layout")],
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

        # ── Help ──
        if action == "help":
            caption = (
                "<b>🧪 Senku — Distribution · Help</b>\n\n"
                "<b>How distribution works</b>\n"
                "1. Open <b>📋 Tasks</b> to see titles awaiting a content pack\n"
                "2. <b>📢 Create Channel</b> spins up the channel + profile picture\n"
                "3. <b>🧪 Generate</b> builds the info card, season separators,\n"
                "   watch guide, footer, and stickers — each editable\n"
                "4. Approve, and the publisher locks it in\n\n"
                "<i>Everything here is button-driven — no commands required.</i>"
            )
            await send_screen(
                client, q.message.chat.id,
                Screen(caption=caption, image=pick_artwork(bot),
                       keyboard=InlineKeyboardMarkup(
                           [[InlineKeyboardButton("◀ Back", callback_data=cb(bot, "home"))]])),
                old_msg=q.message)
            await q.answer()
            return

        await q.answer(f"Action “{action}” not wired yet.", show_alert=True)

    # ── /start ────────────────────────────────────────────────────────────────
    # Rich UI: sticker → loading animation → welcome screen with inline keyboard
    # and Senku-themed artwork (images/senku/).
    @client.on_message(filters.command("start"))
    async def _start(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen
        from nekofetch.ui.components import cb, keyboard
        from nekofetch.ui.artwork import pick_artwork
        from kurosoden.shared.ui_helpers import send_rich_welcome

        rows = [
            [("📋 Tasks", cb("senku", "tasks")),
             ("🧪 Generate", cb("senku", "generate"))],
            [("📢 Create Channel", cb("senku", "create"))],
            [("⚙️ Settings", cb("senku", "settings")),
             ("❓ Help", cb("senku", "help"))],
        ]
        screen = Screen(
            caption=(
                "<b>🧪 Senku Ishigami — Distribution</b>\n\n"
                "<i>\"Ten billion percent — this channel will be perfect.\"</i>\n\n"
                "I handle distribution:\n"
                "• Guide channel creation\n"
                "• Generate info cards & stickers\n"
                "• Create season separators & watch guides\n"
                "• Add footers and branding"
            ),
            image=pick_artwork("senku"),
            keyboard=keyboard(*rows),
        )
        await send_rich_welcome(client, container, message, screen)

    # ── /settings ─────────────────────────────────────────────────────────────
    @client.on_message(filters.command("settings"))
    async def _settings(_: Client, message: Message) -> None:
        from nekofetch.ui.screens import Screen, send_screen
        from nekofetch.ui.components import cb, keyboard

        screen = Screen(
            caption="<b>⚙️ Senku Settings</b>\n\n"
                     "Configure distribution preferences and branding.",
            keyboard=keyboard(
                [("Branding", cb("senku", "set", "branding")),
                 ("Content Layout", cb("senku", "set", "layout"))],
                [("Back", cb("senku", "home"))],
            ),
            image=pick_artwork("senku"),
        )
        await send_screen(client, message.chat.id, screen)

    return client
