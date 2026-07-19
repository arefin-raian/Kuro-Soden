"""Index channel service — dynamic, shift-capable index maintenance.

Maintains stylized, per-letter index posts in a dedicated channel using the
new short-bar format with HTML bold. Supports **dynamic shifting**: when a
letter section overflows Telegram's 1024-char caption limit, the next section
is rebranded (e.g. B → A(2)), all subsequent sections shift down, the last
reserved post is consumed, and the poster button grid is rebuilt.

State is persisted in the ``index_sections`` PostgreSQL table so it survives
restarts. On first run the table must be seeded with the existing channel
message IDs (see ``seed_index_sections``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from sqlalchemy import distinct, select

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.infrastructure.database.postgres.models import IndexSection, StoragePack
from nekofetch.infrastructure.database.postgres.session import session_scope

log = get_logger(__name__)

# Telegram photo caption character limit (leaving 24-char safety margin).
_CAPTION_LIMIT = 1000

# Number of reserved posts to add when they run out.
_RESERVED_BATCH = 10

# Minimum reserved slots before auto-adding more.
_RESERVED_MIN = 3

# Button labels (exact Unicode small caps from old channel).
_MAIN_BTN = "ᴍᴀɪɴ ᴄʜᴀɴɴᴇʟ"
_TOP_BTN = "ɢᴏ ᴛᴏ ᴛᴏᴘ"

# Image directory for letter graphics (absolute, CWD-independent).
_IMG_DIR = Path(__file__).resolve().parents[3] / "index_data" / "index-images"

# Poster caption (Unicode bold heading, HTML bold subtitle).
_POSTER_CAP = (
    "📍[ 𝗜𝗻𝗱𝗲𝘅 𝗼𝗳 𝗔𝗻𝗶𝗺𝗲 𝗪𝗲𝗲𝗯𝘀 ] ----\n\n"
    "<b>Use the buttons below to choose a letter and quickly find"
    " your favorite shows 🎬🔥</b>"
)

# Reserved post caption template.
_RESERVED_CAP = "█▓▒░<b> RESERVED FOR FUTURE </b>░▒▓█"
_RESERVED_IMG = "https://files.catbox.moe/cp9nkw.png"

# User-provided divider sticker.
_DIVIDER = (
    "CAACAgUAAxkBAAJAhmpLZLtVdyR7k9JYI3_iqUJVR_zT"
    "AAJOFwACoa8gVlT9gR8Fr550PAQ"
)

# Main channel link for letter buttons.
_MAIN_LINK = "https://t.me/AniXWeebs"

# ── Seed ────────────────────────────────────────────────────────────────────

_INITIAL_LETTERS = [
    "#", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L",
    "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
]

# Message IDs from the rebuilt channel (must match the actual channel).
# fmt: off
_INITIAL_MSG_IDS = [
    174,  # #
    176, 178, 180, 182, 184, 186, 188, 190, 192, 194,  # A-J
    196, 198, 200, 202, 204, 206, 208, 210, 212, 214,  # K-T
    216, 218, 220, 222, 224, 226,                        # U-Z
]
# Reserved message IDs (label=None initially).
_INITIAL_RESERVED = [
    228, 230, 232, 234, 236, 238, 240, 242, 244, 246,
]
# fmt: on

_POSTER_MSG_ID = 171


async def seed_index_sections(session_maker) -> None:
    """Populate index_sections from the hardcoded channel layout.

    Idempotent — only runs when the table is empty.
    """
    async with session_scope(session_maker) as session:
        existing = (await session.execute(select(IndexSection))).scalars().first()
        if existing:
            return

        order = 1
        for i, letter in enumerate(_INITIAL_LETTERS):
            session.add(IndexSection(
                sort_order=order, label=letter, base_letter=letter,
                message_id=_INITIAL_MSG_IDS[i],
            ))
            order += 1

        for mid in _INITIAL_RESERVED:
            session.add(IndexSection(
                sort_order=order, label=None, base_letter=None,
                message_id=mid,
            ))
            order += 1

        log.info("index.sections.seeded", letters=len(_INITIAL_LETTERS),
                 reserved=len(_INITIAL_RESERVED))


# ── Caption rendering ────────────────────────────────────────────────────────

def _strip_bullet(title: str) -> str:
    """Drop any leading ``⦿`` (and surrounding space) a title already carries.

    Empty index cards are seeded with a bare ``⦿`` bullet, and some legacy
    titles arrive with the bullet baked in. Without this, prepending the
    template bullet yields a doubled ``⦿ ⦿ Name``. Strip first, then format.
    """
    return title.lstrip().removeprefix("⦿").strip()


def _letter_caption(label: str, titles: list[str]) -> str:
    """Build a bold-HTML caption for a letter section.

    Format::

        <b>•────────•°• A •°•────────•</b>

        <b>⦿ Title 1</b>
        <b>⦿ Title 2</b>

        <b>•─────────────────────•</b>
    """
    header = f"<b>•────────•°• {label} •°•────────•</b>"
    body = ("\n".join(f"<b>⦿ {_strip_bullet(t)}</b>" for t in titles)
            if titles else "<b>⦿</b>")
    footer = "<b>•─────────────────────•</b>"
    return f"{header}\n\n{body}\n\n{footer}"


def _chunk_titles(titles: list[str], label: str) -> list[list[str]]:
    """Split titles into chunks that fit within Telegram's caption limit."""
    chunks: list[list[str]] = []
    current: list[str] = []
    # Use a worst-case label like "A(99)" to size the header accurately.
    header_len = len(_letter_caption(label + "(99)", []))
    current_len = header_len

    for title in titles:
        entry = f"<b>⦿ {_strip_bullet(title)}</b>"
        entry_len = len(entry) + 1  # +1 for newline
        if current_len + entry_len > _CAPTION_LIMIT:
            chunks.append(current)
            current = [title]
            current_len = header_len + entry_len
        else:
            current.append(title)
            current_len += entry_len

    if current:
        chunks.append(current)
    return chunks


# ── Service ──────────────────────────────────────────────────────────────────

class IndexChannelService:
    # ── Per-letter lock to prevent concurrent shifts from corrupting
    # the label-to-message mapping (two publishes racing on the same letter).
    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, container: Container) -> None:
        self._c = container
        self.cfg = container.config.index_channel

    def _active(self) -> bool:
        client = getattr(self._c, "admin_client", None)
        return bool(self.cfg.enabled and self.cfg.channel_id != 0 and client is not None)

    @staticmethod
    def letter_of(title: str) -> str:
        for ch in title:
            if ch.isalpha():
                return ch.upper()
            if ch.isdigit():
                return "#"
        return "#"

    async def _titles_for_letter(self, base_letter: str) -> list[str]:
        # DB-level filter — avoids loading all titles into Python memory.
        # For '#' (digit-starting titles), use PostgreSQL regex ^[0-9];
        # for A-Z, use ILIKE for case-insensitive letter matching.
        if base_letter == "#":
            cond = StoragePack.anime_title.op("~")(r"^[0-9]")
        else:
            cond = StoragePack.anime_title.ilike(f"{base_letter}%")
        async with session_scope(self._c.pg_sessionmaker) as session:
            rows = (
                await session.execute(
                    select(distinct(StoragePack.anime_title)).where(cond)
                )
            ).scalars().all()
        return sorted(rows)

    async def _all_active_sections(self) -> list[IndexSection]:
        """Return all sections with a label, ordered by sort_order."""
        async with session_scope(self._c.pg_sessionmaker) as session:
            result = await session.execute(
                select(IndexSection)
                .where(IndexSection.label.isnot(None))
                .order_by(IndexSection.sort_order)
            )
            return list(result.scalars().all())

    async def _count_reserved(self) -> int:
        async with session_scope(self._c.pg_sessionmaker) as session:
            return await self._count_reserved_in_session(session)

    async def _count_reserved_in_session(self, session) -> int:
        result = await session.execute(
            select(IndexSection).where(IndexSection.label.is_(None))
        )
        return len(list(result.scalars().all()))

    async def _get_poster_id(self) -> int:
        """Return the poster message ID (hardcoded from rebuild)."""
        return _POSTER_MSG_ID

    # ── Refresh ─────────────────────────────────────────────────────────

    async def refresh_letter(self, base_letter: str, _retry: int = 0) -> int | None:
        """Rebuild all chunks for ``base_letter``; shift if needed.

        Returns the first chunk's message ID (for ``entry_link``).
        The ``_retry`` parameter prevents infinite recursion when
        reserved-post creation keeps failing.
        """
        if not self._active():
            return None

        # Acquire per-letter lock so two concurrent publishes for the same
        # letter can't double-shift and corrupt the section mapping.
        lock = IndexChannelService._locks.setdefault(base_letter, asyncio.Lock())
        async with lock:
            return await self._refresh_letter_locked(base_letter, _retry)

    async def _refresh_letter_locked(self, base_letter: str, _retry: int = 0) -> int | None:
        """Core refresh logic — called from ``refresh_letter`` under the per-letter lock."""
        titles = await self._titles_for_letter(base_letter)
        if not titles:
            return None

        chunks = _chunk_titles(titles, base_letter)
        client = self._c.admin_client
        first_mid: int | None = None

        async with session_scope(self._c.pg_sessionmaker) as session:
            # Get existing sections for this base letter
            existing = (
                await session.execute(
                    select(IndexSection)
                    .where(IndexSection.base_letter == base_letter)
                    .order_by(IndexSection.sort_order)
                )
            ).scalars().all()
            existing = list(existing)

            # If more chunks than slots, shift down starting from the
            # section *after* the last existing chunk for this letter.
            if len(chunks) > len(existing):
                if not existing:
                    log.error("index.refresh.no_slot", base_letter=base_letter,
                              hint="letter has no pre-allocated section")
                    return None

                needed = len(chunks) - len(existing)
                reserved_count = await self._count_reserved_in_session(session)
                if needed > reserved_count:
                    if _retry >= 3:
                        log.error("index.refresh.max_retries", base_letter=base_letter)
                        return None
                    log.warning("index.refresh.out_of_reserved",
                                needed=needed, available=reserved_count,
                                base_letter=base_letter)
                    await session.commit()
                    await self._add_reserved_batch()
                    # Retry with fresh session so the new reserved posts
                    # are visible to the next refresh_letter call.
                    return await self._refresh_letter_locked(base_letter, _retry + 1)

                # from_order targets the next section (e.g. B becomes A(2)).
                from_order = existing[-1].sort_order + 1
                for _ in range(needed):
                    await self._shift_down_in_session(session, from_order)
                    from_order += 1  # next shift targets the slot that was just vacated
                # Re-fetch after shift
                existing = (
                    await session.execute(
                        select(IndexSection)
                        .where(IndexSection.base_letter == base_letter)
                        .order_by(IndexSection.sort_order)
                    )
                ).scalars().all()
                existing = list(existing)

            # Edit or clear each section
            for idx in range(len(existing)):
                if idx < len(chunks):
                    chunk = chunks[idx]
                    section = existing[idx]
                    label = base_letter if idx == 0 else f"{base_letter}({idx + 1})"
                    caption = _letter_caption(label, chunk)

                    # Check if image needs changing
                    old_label = section.label or ""
                    needs_image = not old_label.startswith(base_letter) or section.base_letter != base_letter

                    section.label = label
                    section.base_letter = base_letter

                    if idx == 0:
                        first_mid = cast(int, section.message_id)

                    try:
                        if needs_image:
                            img_path = _IMG_DIR / f"{base_letter}.jpg"
                            if img_path.exists():
                                await client.edit_message_media(
                                    self.cfg.channel_id, cast(int, section.message_id),
                                    media=InputMediaPhoto(
                                        media=str(img_path), caption=caption,
                                        parse_mode=ParseMode.HTML,
                                    ),
                                    reply_markup=self._letter_buttons(),
                                )
                                continue
                        await client.edit_message_caption(
                            self.cfg.channel_id, cast(int, section.message_id),
                            caption=caption, parse_mode=ParseMode.HTML,
                            reply_markup=self._letter_buttons(),
                        )
                    except Exception as exc:
                        if "MESSAGE_NOT_MODIFIED" not in str(exc):
                            log.warning("index.refresh.failed", label=label, error=str(exc))
                else:
                    # Shrinking chunks — clear the caption but keep the
                    # label/base_letter so the section remains in the
                    # poster grid (just with no titles showing).
                    section = existing[idx]
                    empty_cap = _letter_caption(section.label or "?", [])
                    try:
                        await client.edit_message_caption(
                            self.cfg.channel_id, cast(int, section.message_id),
                            caption=empty_cap, parse_mode=ParseMode.HTML,
                            reply_markup=self._letter_buttons(),
                        )
                    except Exception as exc:
                        if "MESSAGE_NOT_MODIFIED" not in str(exc):
                            log.warning("index.refresh.clear_failed",
                                        section_id=section.message_id, error=str(exc))

            await session.commit()

        # ── After commit: check reserved count & rebuild poster ─────────
        # Must happen here (outside the session) so we don't nest commits.
        if await self._count_reserved() < _RESERVED_MIN:
            if not await self._add_reserved_batch():
                log.warning("index.refresh.reserved_add_failed", base_letter=base_letter)

        await self._rebuild_poster()
        return first_mid

    async def _shift_down_in_session(self, session, from_order: int) -> None:
        """Shift sections starting at ``from_order`` down by one.

        MUST be called inside an active session_scope.
        """
        result = await session.execute(
            select(IndexSection)
            .where(IndexSection.sort_order >= from_order)
            .order_by(IndexSection.sort_order)
        )
        sections = list(result.scalars().all())
        if not sections:
            return

        first = sections[0]

        # ── Save old labels BEFORE we mutate anything ──────────────────
        old_labels: list[tuple[str | None, str | None]] = [
            (s.label, s.base_letter) for s in sections
        ]

        # Find the previous section's base letter
        prev_result = await session.execute(
            select(IndexSection)
            .where(IndexSection.sort_order == from_order - 1)
        )
        prev = prev_result.scalars().first()
        prev_base = prev.base_letter if prev and prev.base_letter else "?"

        # Count existing chunks for the overflow letter
        count_result = await session.execute(
            select(IndexSection).where(IndexSection.base_letter == prev_base)
        )
        existing_count = len(list(count_result.scalars().all()))

        # Store values we need after the shift for image change
        new_first_label = f"{prev_base}({existing_count + 1})"
        first_msg_id = first.message_id

        # Rebrand the first section
        first.label = new_first_label
        first.base_letter = prev_base

        # Shift remaining sections down using the SAVED old labels
        for i in range(1, len(sections)):
            current = sections[i]
            prev_old_label, prev_old_base = old_labels[i - 1]
            if current.label is None:
                # Consume reserved — inherit the label that was in the
                # previous slot *before* we started shifting.
                current.label = prev_old_label
                current.base_letter = prev_old_base
                break  # Only one reserved gets consumed per shift
            current.label = prev_old_label
            current.base_letter = prev_old_base

        # Change image for rebranded section
        if first_msg_id:
            client = self._c.admin_client
            img_path = _IMG_DIR / f"{prev_base}.jpg"
            if img_path.exists():
                try:
                    temp_cap = _letter_caption(new_first_label, [])
                    await client.edit_message_media(
                        self.cfg.channel_id, first_msg_id,
                        media=InputMediaPhoto(
                            media=str(img_path), caption=temp_cap,
                            parse_mode=ParseMode.HTML,
                        ),
                        reply_markup=self._letter_buttons(),
                    )
                except Exception as exc:
                    log.warning("index.shift.image_failed", label=new_first_label, error=str(exc))

        log.info("index.shifted", from_order=from_order, new_label=new_first_label)

    async def _add_reserved_batch(self) -> bool:
        """Post _RESERVED_BATCH new reserved posts at the end of the channel.

        Returns True if all posts were sent successfully, False otherwise.
        """
        if not self._active():
            return False

        client = self._c.admin_client
        async with session_scope(self._c.pg_sessionmaker) as session:
            # Find max sort_order
            result = await session.execute(
                select(IndexSection.sort_order).order_by(IndexSection.sort_order.desc()).limit(1)
            )
            max_order = result.scalars().first() or 0

            all_ok = True
            for i in range(_RESERVED_BATCH):
                # Divider sticker
                try:
                    await client.send_sticker(self.cfg.channel_id, _DIVIDER)
                except Exception as exc:
                    log.warning("index.reserved.divider_failed", error=str(exc))

                # Reserved post with image
                try:
                    sent = await client.send_photo(
                        self.cfg.channel_id, _RESERVED_IMG,
                        caption=(f"{_RESERVED_CAP}\n\n"
                                 f"<i>Slot {i + 1}/{_RESERVED_BATCH}</i>"),
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._letter_buttons(),
                    )
                    max_order += 1
                    session.add(IndexSection(
                        sort_order=max_order, label=None, base_letter=None,
                        message_id=sent.id,
                    ))
                    log.info("index.reserved.added", msg_id=sent.id, order=max_order)
                except Exception as exc:
                    log.warning("index.reserved.add_failed", error=str(exc))
                    all_ok = False
                    await asyncio.sleep(2)  # brief pause before next attempt

            await session.commit()
            return all_ok

    # ── Poster ──────────────────────────────────────────────────────────

    async def _rebuild_poster(self) -> None:
        """Rebuild the poster's 3-column letter button grid."""
        if not self._active():
            return

        sections = await self._all_active_sections()
        if not sections:
            return

        client = self._c.admin_client
        poster_id = await self._get_poster_id()
        username = "AniXWeebs_Index"

        rows = []
        row = []
        for sec in sections:
            if sec.label and sec.message_id:
                row.append(InlineKeyboardButton(
                    sec.label, url=f"https://t.me/{username}/{sec.message_id}"
                ))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        try:
            await client.edit_message_caption(
                self.cfg.channel_id, poster_id,
                caption=_POSTER_CAP, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(rows),
            )
            log.info("index.poster.rebuilt", buttons=sum(len(r) for r in rows))
        except Exception as exc:
            if "MESSAGE_NOT_MODIFIED" not in str(exc):
                log.warning("index.poster.rebuild_failed", error=str(exc))

    # ── Buttons / links ──────────────────────────────────────────────────

    def _letter_buttons(self) -> InlineKeyboardMarkup:
        poster_id = _POSTER_MSG_ID
        username = "AniXWeebs_Index"
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                _MAIN_BTN, url=_MAIN_LINK,
            ),
            InlineKeyboardButton(
                _TOP_BTN, url=f"https://t.me/{username}/{poster_id}",
            ),
        ]])

    async def entry_link(self, title: str) -> str | None:
        """Return a t.me link to the index post containing ``title``."""
        if not self._active():
            return None

        base = self.letter_of(title)
        titles = await self._titles_for_letter(base)
        if not titles:
            return None

        chunks = _chunk_titles(titles, base)
        async with session_scope(self._c.pg_sessionmaker) as session:
            sections = (
                await session.execute(
                    select(IndexSection)
                    .where(IndexSection.base_letter == base)
                    .order_by(IndexSection.sort_order)
                )
            ).scalars().all()
            sections = list(sections)

        for idx, chunk in enumerate(chunks):
            if title in chunk and idx < len(sections) and sections[idx].message_id:
                username = "AniXWeebs_Index"
                return f"https://t.me/{username}/{sections[idx].message_id}"

        # Fallback: first section
        if sections and sections[0].message_id:
            username = "AniXWeebs_Index"
            return f"https://t.me/{username}/{sections[0].message_id}"

        return None
