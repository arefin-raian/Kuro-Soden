"""Automatic distribution-entity creation — bots via @BotFather, channels via userbot.

A bot's token AND its profile photo can only be obtained/set through @BotFather, so
this drives a real BotFather conversation with the user account from the userbot pool:

    /newbot → <name> → <username> → token
    /setuserpic → @username → <photo>
    /setdescription / /setabouttext → @username → <text>

A channel requires only a Pyrogram ``create_channel`` call — no BotFather is involved.

Capacity model (configurable):
    • max 20 bots per account
    • max 10 channels per account
When the bot limit is exhausted for a userbot session, the orchestrator falls back
on channel creation.

The created token/chat_id is then handed to :class:`BotManagementService` which
validates, encrypts, stores, and (for bots) brings them online.

⚠️ The BotFather conversation is wording-sensitive and rate-limited; this is written
defensively (token regex, username-taken retries, bounded waits) but should be
exercised live once — it cannot be unit-tested against the real BotFather.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import httpx
from sqlalchemy import func, select

from nekofetch.core.container import Container
from nekofetch.core.exceptions import NekoFetchError
from nekofetch.core.logging import get_logger
from nekofetch.domain.enums import AudioType
from nekofetch.services.bot_naming import format_bot_name, format_bot_username

log = get_logger(__name__)

_BOTFATHER = "BotFather"
_TOKEN_RE = re.compile(r"(\d{6,}:[A-Za-z0-9_-]{30,})")
# subbed → Japanese audio, dubbed → English audio (dual = both).
_AUDIO_LANGS = {
    AudioType.SUBBED.value: "japanese",
    AudioType.DUBBED.value: "english",
    AudioType.DUAL_AUDIO.value: "english",
}


class BotFactory:
    def __init__(self, container: Container) -> None:
        self._c = container
        self._pool = None

    def _userbot(self):
        if self._pool is None:
            from nekofetch.sources.telegram.userbot import UserbotPool

            self._pool = UserbotPool.from_env(
                self._c.env.telegram_api_id, self._c.env.telegram_api_hash,
                str(self._c.env.session_path),
            )
        return self._pool

    # ── public entry ─────────────────────────────────────────────────────────────
    async def create_for_anime(self, anime_doc_id: str) -> "BotInfo":
        """Create + configure a distribution bot for a published title, then register
        it. Returns the BotInfo from BotManagementService.

        Checks capacity first: if bots per account are exhausted, creates a channel
        instead (calls ``create_for_anime_channel``).
        """
        if not self._c.config.features.distribution_bots:
            raise NekoFetchError("distribution_bots feature is disabled")

        cfg = self._c.config.bot
        counts = await self._count_entities()

        # Exhausted bot limit → fall back to channel.
        if counts["bots"] >= cfg.max_bots_per_account:
            log.info("botfactory.bot_limit_exhausted", bots=counts["bots"],
                     max=cfg.max_bots_per_account)
            return await self.create_for_anime_channel(anime_doc_id)

        meta = await self._gather(anime_doc_id)
        name = format_bot_name(meta["english"], meta["romaji"],
                               audios=meta["audios"], languages=meta["languages"],
                               qualities=meta["qualities"])
        username = format_bot_username(meta["english"] or meta["romaji"] or "anime",
                                       anime_doc_id, is_channel=False)
        description = self._build_description(meta)
        about = self._build_about(meta)
        avatar = await self._fetch_avatar(meta["english"] or meta["romaji"] or "")

        log.info("botfactory.create", anime=anime_doc_id, name=name, username=username)
        token = await self._userbot().execute(
            lambda c: self._botfather_create(c, name, username, avatar, description, about)
        )
        if avatar:
            try:
                avatar.unlink()
            except OSError:
                pass

        from nekofetch.services.bot_management_service import BotManagementService, BotInfo

        return await BotManagementService(self._c).register(
            token, name=name, anime_doc_id=anime_doc_id,
        )

    async def create_for_anime_channel(self, anime_doc_id: str) -> "BotInfo":
        """Create a public channel for a published title via the userbot account.

        Channels support proper ``t.me/c/`` deep links (unlike bots in private
        chats), so the quality text in the watch guide can be clickable.
        Content generation and delivery are identical to bots.
        """
        if not self._c.config.features.distribution_bots:
            raise NekoFetchError("distribution_bots feature is disabled")

        cfg = self._c.config.bot
        counts = await self._count_entities()
        if counts["channels"] >= cfg.max_channels_per_account:
            raise NekoFetchError(
                f"Channel limit exhausted ({counts['channels']}/{cfg.max_channels_per_account})"
            )

        meta = await self._gather(anime_doc_id)
        name = format_bot_name(meta["english"], meta["romaji"],
                               audios=meta["audios"], languages=meta["languages"],
                               qualities=meta["qualities"])
        username = format_bot_username(meta["english"] or meta["romaji"] or "anime",
                                       anime_doc_id, is_channel=True)

        log.info("botfactory.create_channel", anime=anime_doc_id, name=name, username=username)

        from nekofetch.services.bot_management_service import BotManagementService, BotInfo

        chat_id = await self._userbot().execute(
            lambda c: self._create_channel(c, name, username)
        )

        return await BotManagementService(self._c).register_channel(
            chat_id, name=name, username=username, anime_doc_id=anime_doc_id,
        )

    # ── capacity ────────────────────────────────────────────────────────────────
    async def _count_entities(self) -> dict:
        """Count bots and channels across all userbot accounts."""
        from nekofetch.infrastructure.database.postgres.models import DistributionBot
        from nekofetch.infrastructure.database.postgres.session import session_scope

        async with session_scope(self._c.pg_sessionmaker) as session:
            bot_count = (
                await session.execute(
                    select(func.count()).where(
                        DistributionBot.is_channel.is_(False),
                        DistributionBot.enabled.is_(True),
                    )
                )
            ).scalar_one()
            channel_count = (
                await session.execute(
                    select(func.count()).where(
                        DistributionBot.is_channel.is_(True),
                        DistributionBot.enabled.is_(True),
                    )
                )
            ).scalar_one()
        return {"bots": bot_count, "channels": channel_count}

    # ── channel creation ────────────────────────────────────────────────────────
    async def _create_channel(self, client, name: str, username: str) -> int:
        """Create a public channel via Pyrogram's userbot client.

        Returns the channel's chat_id (negative int, e.g. -1001234567890).
        """
        chat = await client.create_channel(title=name, username=username)
        chat_id = chat.id  # type: ignore[union-attr]
        log.info("botfactory.channel_created", name=name, username=username,
                 chat_id=chat_id)
        return chat_id

    # ── metadata ─────────────────────────────────────────────────────────────────
    async def _gather(self, anime_doc_id: str) -> dict:
        """Resolve the bot's display-name ingredients from Postgres.

        Audios/qualities come from ``StoragePack`` (the destination-of-truth
        table for what's ACTUALLY available in the storage channel), not
        ``MediaFile`` (whose rows can become stale once the upload-and-clean
        step has finished). The bot name needs all three pieces (audio type,
        language label, qualities) so the user sees a single identifiable
        tag inside Telegram's 64-char name cap.
        """
        from sqlalchemy import select

        from nekofetch.infrastructure.database.postgres.models import (
            Request, StoragePack,
        )
        from nekofetch.infrastructure.database.postgres.session import session_scope

        english = romaji = ""
        audios: set = set()
        quals: set = set()
        async with session_scope(self._c.pg_sessionmaker) as session:
            # Strip anilist: prefix when searching the DB — the request's
            # anime_doc_id field stores the clean title, source_ref is the
            # fallback that may carry the anilist: prefix.
            lookup = anime_doc_id
            if lookup.startswith("anilist:"):
                lookup = lookup[len("anilist:"):]
            req = (await session.execute(
                select(Request).where(Request.anime_doc_id == lookup)
                .order_by(Request.id.desc())
            )).scalars().first()
            if req is None:
                req = (await session.execute(
                    select(Request).where(Request.source_ref == f"anilist:{lookup}")
                    .order_by(Request.id.desc())
                )).scalars().first()
            if req is not None:
                fr = req.franchise_data or {}
                english = fr.get("english") or req.anime_title or ""
                romaji = fr.get("romaji") or ""
            # ── Storage packs are the canonical source of "what does this title
            # actually carry": every pack has a non-null audio + resolution
            # column tied to its anime_doc_id, so we get a definitive set
            # instead of living with whatever MediaFile still has around.
            packs = (await session.execute(
                select(StoragePack).where(
                    StoragePack.anime_doc_id == anime_doc_id,
                    StoragePack.enabled.is_(True),
                )
            )).scalars().all()
            audios = {p.audio.value for p in packs if p.audio is not None}
            quals = {p.resolution for p in packs if p.resolution}
        languages = {_AUDIO_LANGS.get(a) for a in audios}
        if AudioType.DUAL_AUDIO.value in audios:
            languages.update({"english", "japanese"})
        if AudioType.MULTI.value in audios:
            languages.update({"english", "japanese", "hindi"})
        languages.discard(None)
        # Sort qualities by resolution.
        _QORDER = {"360p": 0, "480p": 1, "540p": 2, "720p": 3, "1080p": 4, "2160p": 5}
        quality_list = sorted(quals, key=lambda q: _QORDER.get(q, 99)) if quals else []
        return {"english": english, "romaji": romaji, "audios": audios,
                "languages": languages, "qualities": quality_list}

    # ── AniXWeebs branding block ────────────────────────────────────────────────
    # The owner's exact about/description text. Telegram enforces:
    #   * /setdescription   — 512 char limit (long form)
    #   * /setabouttext     —  120 char limit (short form)
    # This block fits the long form; the short form trims to the most-essential
    # two lines so the limit is respected without dropping information.
    _BRANDING_DESCRIPTION = (
        "➥ 𝗠𝗮𝗶𝗻 𝗖𝗵𝗮𝗻𝗻𝗲𝗹: @AniXWeebs\n"
        "➥ 𝗜𝗻𝗱𝗲𝘅: @AniXWeebs_Index\n"
        "➥ 𝗢𝗻𝗴𝗼𝗶𝗻𝗴: @Ongoing_AniXWeebs\n"
        "➥ 𝗠𝗼𝘃𝗶𝗲𝘀: @AniMovieXWeebs\n"
        "➥ 𝗡𝗲𝘁𝘄𝗼𝗿𝗸: @WeebsXServer"
    )
    # Trimmed for the 120-char short-description (about) Telegram limit.
    _BRANDING_ABOUT = "➥ 𝗠𝗮𝗶𝗻 𝗖𝗵𝗮𝗻𝗻𝗲𝗹: @AniXWeebs | 𝗡𝗲𝘁𝘄𝗼𝗿𝗸: @WeebsXServer"

    @staticmethod
    def _build_description(meta: dict) -> str:
        """Build the bot's full description (Telegram /setdescription, 512 chars).

        Uses the owner's brand block by default and prepends the title so the
        bot's profile shows both WHAT it serves and WHERE the network lives.
        An operator can override via ``cfg.bot.description_text``.
        """
        from nekofetch.core.config import get_app_config
        cfg = get_app_config()
        override = (getattr(cfg.bot, "description_text", "") or "").strip()
        if override:
            return override[:512]
        title = (meta.get("english") or meta.get("romaji") or "").strip()
        # Fallback when override is unset AND there's nothing to brand against.
        if not (title or BotFactory._BRANDING_DESCRIPTION):
            return ""
        # BRANDING_DESCRIPTION is already ≤512 chars on its own. Prepending the
        # title in plain text (no newline glitch) keeps both readable.
        if not title:
            return BotFactory._BRANDING_DESCRIPTION[:512]
        return f"{title}\n\n{BotFactory._BRANDING_DESCRIPTION}"[:512]

    @staticmethod
    def _build_about(meta: dict) -> str:
        """Build the bot's short description (Telegram /setabouttext, 120 chars).

        Returns a compact two-line block trimmed to fit the Telegram limit.
        Operators may override via ``cfg.bot.about_text``.
        """
        from nekofetch.core.config import get_app_config
        cfg = get_app_config()
        override = (getattr(cfg.bot, "about_text", "") or "").strip()
        if override:
            return override[:120]
        title = (meta.get("english") or meta.get("romaji") or "").strip()
        # When no title is available, return the trimmed brand block as-is.
        # When title IS present, prepend it and truncate to 120 chars so the
        # short-description stays within Telegram's hard limit.
        if not title:
            return BotFactory._BRANDING_ABOUT[:120]
        joined = f"{title} | {BotFactory._BRANDING_ABOUT}"
        if len(joined) <= 120:
            return joined
        return BotFactory._BRANDING_ABOUT[:120]

    async def _fetch_avatar(self, title: str) -> Path | None:
        """Download a DIFFERENT TMDB poster (rank 1) for the bot's profile photo.

        We deliberately do NOT composite a background or overlay here: the user
        wants the raw poster uploaded as-is and let Telegram handle the
        square crop.
        """
        if not title:
            return None
        try:
            # w780 (not w500) keeps the poster sharp after Telegram's profile
            # cropper; ``original`` is rejected sometimes by BotFather's
            # /setuserpic on multi-MB movie posters, so w780 is the safe choice.
            url = await self._c.tmdb.poster_for(title, size="w780", rank=1)
        except Exception:  # noqa: BLE001
            url = None
        if not url:
            return None
        dest = Path(self._c.env.storage_path) / "work" / "_avatars" / f"{abs(hash(title))}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cli:
                r = await cli.get(url)
                r.raise_for_status()
                dest.write_bytes(r.content)
            return dest
        except Exception as exc:  # noqa: BLE001
            log.warning("botfactory.avatar.failed", error=str(exc))
            return None

    # ── BotFather conversation ───────────────────────────────────────────────────
    async def _botfather_create(self, client, name: str, username: str,
                                avatar: Path | None, description: str,
                                about: str = "") -> str:
        await self._say(client, "/newbot")
        await self._say(client, name)
        reply = await self._say(client, username)

        attempts = 0
        while reply and re.search(r"taken|invalid|sorry|too short|letters", reply, re.I):
            attempts += 1
            if attempts > 8:
                raise NekoFetchError(f"BotFather rejected all usernames: {reply[:120]}")
            username = self._bump(username, attempts)
            reply = await self._say(client, username)

        m = _TOKEN_RE.search(reply or "")
        if not m:
            raise NekoFetchError(f"BotFather did not return a token: {(reply or '')[:160]}")
        token = m.group(1)

        # Profile photo (must go through BotFather).
        if avatar and avatar.exists():
            try:
                await self._say(client, "/setuserpic")
                await self._say(client, f"@{username}")
                await client.send_photo(_BOTFATHER, str(avatar))
                await asyncio.sleep(2.0)
            except Exception as exc:  # noqa: BLE001
                log.warning("botfactory.setuserpic.failed", error=str(exc))

        # Placeholder description + about (the owner edits these later via en.json).
        if description:
            for cmd, text in (("/setdescription", description),
                              ("/setabouttext", (about or description)[:120])):
                try:
                    await self._say(client, cmd)
                    await self._say(client, f"@{username}")
                    await self._say(client, text)
                except Exception as exc:  # noqa: BLE001
                    log.warning("botfactory.setinfo.failed", cmd=cmd, error=str(exc))

        log.info("botfactory.created", username=username)
        return token

    @staticmethod
    def _bump(username: str, n: int) -> str:
        stem = username[:-3] if username.endswith("bot") else username
        stem = stem.rstrip("_0123456789")[: 32 - len(f"{n}bot")]
        return f"{stem}{n}bot"

    async def _say(self, client, text: str, *, wait: float = 2.5) -> str:
        """Send a line to BotFather and return its next reply text (best-effort)."""
        await client.send_message(_BOTFATHER, text)
        await asyncio.sleep(wait)
        async for msg in client.get_chat_history(_BOTFATHER, limit=1):
            return msg.text or msg.caption or ""
        return ""
