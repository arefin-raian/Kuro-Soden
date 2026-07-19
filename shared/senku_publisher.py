"""Senku's channel publisher — Phase 4 of the distribution flow.

Once the admin confirms the watch order (Phase 4), this module posts the finished
content pack straight into the distribution channel Senku's client already admins.
It is the manual-flow counterpart to the automated distribution bot: same cards,
same choreography, same URL buttons — just driven by the admin's *confirmed*
watch order rather than a fresh AniList walk.

Why not call :meth:`BotContentService.generate_posts` directly? That method

  * requires a persisted :class:`DistributionBot` row (our channel lives only in
    :class:`DistributionCache`, keyed by request code — there is no bot row), and
  * re-walks AniList to derive the ordering, which would discard the ordering the
    admin just confirmed/edited in Phase 4.

So this publisher *reuses* every card builder on :class:`BotContentService`
(``_build_info_card`` / ``_build_season_card`` / ``_build_franchise_watch_guide``
/ ``_build_season_buttons``) but feeds them a franchise whose ``tv``/``extras``/
``all`` lists are reordered to match the confirmed cache, and bridges the admin's
locally-rendered ``file://`` thumbnails to public catbox URLs so Telegram can
serve them. Posting mirrors the distribution app's ``_send_posts``: divider
stickers between sections, URL buttons from ``button_data.links``, and a pinned
info card + watch guide with the "pinned this message" service notices swept.

Best-effort throughout the *delivery* half: a single failed card is logged and
skipped so a partial channel still reaches users. The *build* half raises on a
hard failure (no packs, no franchise) so the wizard can show ``PUBLISH_FAIL``
rather than pin an empty channel.
"""

from __future__ import annotations

from pathlib import Path

from pyrogram.enums import ParseMode

from nekofetch.core.container import Container
from nekofetch.core.logging import get_logger
from nekofetch.services.bot_render import build_audio_keyboard, resolve_premium_emoji

from kurosoden.shared.distribution_cache import DistributionCache, EntryData

log = get_logger(__name__)

# TV formats, mirrored from bot_content so we split cached entries the same way.
_TV_FORMATS = {"TV", "TV_SHORT", "TV_SPECIAL"}


class PublishError(RuntimeError):
    """Raised when the content pack can't be built (no packs, no franchise)."""


class SenkuPublisher:
    """Post a confirmed distribution channel's content pack into its Telegram chat."""

    def __init__(self, container: Container) -> None:
        self._c = container
        self.cache = DistributionCache(container)

    # ── public entry ───────────────────────────────────────────────────────────

    async def publish(self, client, code: str) -> dict:
        """Build and post the full content pack for ``code`` into its channel.

        Returns a summary dict ``{title, chat_id, posted, pinned}``. Raises
        :class:`PublishError` when there's nothing publishable (no channel,
        no franchise, no packs) so the caller shows a failure card.
        """
        channel = await self.cache.get_channel(code)
        if not channel or not channel.get("chat_id"):
            raise PublishError(f"no verified channel for {code}")
        chat_id = int(channel["chat_id"])

        posts, title = await self._build_posts(code)
        if not posts:
            raise PublishError(f"no content to publish for {code}")

        posted, pinned = await self._send_posts(client, chat_id, posts)
        log.info("senku.publish.done", code=code, chat_id=chat_id,
                 posted=posted, pinned=len(pinned))
        return {"title": title, "chat_id": chat_id, "posted": posted,
                "pinned": pinned}

    # ── build ────────────────────────────────────────────────────────────────────

    async def _build_posts(self, code: str) -> tuple[list[dict], str]:
        """Assemble the ordered post list, reusing BotContentService builders.

        The returned posts are plain dicts (not persisted ``BotContentPost``
        rows — the channel has no bot row); each carries ``caption``, an
        ``image`` (catbox/AniList URL or ``None``), ``button_data``, and the
        ``pinned``/``post_type`` flags the sender needs.
        """
        from nekofetch.services.bot_content import BotContentService

        svc = BotContentService(self._c)

        franchise_cache = await self.cache.get_franchise(code) or await self.cache.ensure(code)
        if not franchise_cache:
            raise PublishError(f"no franchise for {code}")
        anime_doc_id = franchise_cache.get("anime_doc_id") or code
        title = (franchise_cache.get("english") or franchise_cache.get("title")
                 or franchise_cache.get("anime_title") or code)

        entries = await self.cache.get_entries(code)

        # Data the builders need — loaded exactly as generate_posts does.
        packs = await svc._load_packs(anime_doc_id)
        meta = await svc._gather_metadata(anime_doc_id)
        walked = await svc._walk_franchise(anime_doc_id, meta)

        # Reorder the AniList walk to the admin's *confirmed* order, and bridge
        # each entry's locally-rendered thumbnail to a public URL.
        franchise = self._reorder_franchise(walked, entries)
        generated = await self._bridge_thumbnails(code, entries)

        posts: list[dict] = []
        order = 0

        # ── 1. Info card ──
        info_caption, info_default = await svc._build_info_card(meta)
        if info_caption:
            first_tv = franchise["tv"][0] if franchise["tv"] else None
            info_image = svc._pick_card_image(
                generated.get(getattr(first_tv, "anilist_id", None)),
                info_default, meta,
            )
            posts.append({
                "post_type": "info_card", "order": order,
                "caption": info_caption,
                "image": await self._cache_image(info_image),
                "button_data": None, "pinned": True,
            })
            order += 1

        # ── 2. Season cards (confirmed TV order) ──
        for i, entry in enumerate(franchise["tv"], start=1):
            season_packs = [p for p in packs if p.season == i]
            entry_meta = svc._entry_meta(meta, entry)
            gen = generated.get(entry.anilist_id)
            if gen:
                entry_meta["poster_url"] = gen
            caption, image = svc._build_season_card(entry_meta, i, season_packs)
            buttons = await svc._build_season_buttons(season_packs)
            posts.append({
                "post_type": "season_card", "order": order,
                "caption": caption,
                "image": await self._cache_image(image),
                "button_data": buttons, "pinned": False,
            })
            order += 1

        # ── 3. Extra cards (OVA / ONA / Movie / Special) ──
        for entry in franchise["extras"]:
            extra_packs = [
                p for p in packs
                if (p.entry_id is not None and p.entry_id == entry.anilist_id)
                or (p.entry_id is None and p.season is None)
            ]
            entry_meta = svc._entry_meta(meta, entry)
            gen = generated.get(entry.anilist_id)
            if gen:
                entry_meta["poster_url"] = gen
            is_movie = entry.format == "MOVIE" or (
                entry.format in ("OVA", "ONA", "SPECIAL")
                and (entry.episodes or 0) <= 1
            )
            caption, image = svc._build_season_card(entry_meta, 1, extra_packs)
            buttons = await svc._build_season_buttons(extra_packs) if extra_packs else None
            posts.append({
                "post_type": "movie_card" if is_movie else "season_card",
                "order": order, "caption": caption,
                "image": await self._cache_image(image),
                "button_data": buttons, "pinned": False,
            })
            order += 1

        # ── 4. Watch guide (pinned) — reuses the franchise builder, so the
        # release-order listing matches the reordered franchise exactly. ──
        guide = svc._build_franchise_watch_guide(meta, packs, franchise)
        if guide:
            posts.append({
                "post_type": "watch_guide", "order": order,
                "caption": guide, "image": None,
                "button_data": None, "pinned": True,
            })
            order += 1

        # ── 5. Footer ──
        from nekofetch.localization.messages import M, t

        footer_text = self._c.config.bot.footer_text or t(M.BOT_FOOTER)
        footer_image = self._c.config.bot.footer_image_url or None
        posts.append({
            "post_type": "footer", "order": order,
            "caption": footer_text,
            "image": await self._cache_image(footer_image),
            "button_data": None, "pinned": False,
        })

        return posts, title

    def _reorder_franchise(
        self, walked: dict, entries: list[EntryData],
    ) -> dict:
        """Reorder a fresh AniList walk to match the admin's confirmed entries.

        ``walked`` is ``{"tv": [...], "extras": [...], "all": [...]}`` of
        :class:`FranchiseEntry` objects (full metadata). We key those by
        ``anilist_id`` and re-emit them in the cached entry order; any AniList
        entry the admin dropped is excluded, and any cached entry AniList
        couldn't resolve is skipped (it has no card-quality metadata anyway).
        """
        by_id = {
            e.anilist_id: e
            for e in walked.get("all", [])
            if getattr(e, "anilist_id", None) is not None
        }
        ordered: list = []
        for ce in entries:
            if ce.anilist_id is not None and ce.anilist_id in by_id:
                ordered.append(by_id[ce.anilist_id])
        # If the cached entries never carried anilist_ids (bare franchise), fall
        # back to the AniList walk order so the channel still gets cards.
        if not ordered:
            ordered = list(walked.get("all", []))
        tv = [e for e in ordered if e.format in _TV_FORMATS]
        extras = [e for e in ordered if e.format not in _TV_FORMATS]
        return {"tv": tv, "extras": extras, "all": ordered}

    async def _bridge_thumbnails(
        self, code: str, entries: list[EntryData],
    ) -> dict[int, str]:
        """Map ``anilist_id → public thumbnail URL`` for entries the admin rendered.

        Phase 3 stores each rendered card as ``file://<path>`` in the entry's
        selection. Telegram can't serve a local path, so we upload each render
        to catbox once here. A failed upload just omits that entry — the card
        builder falls back to the AniList poster via ``_pick_card_image``.
        """
        from nekofetch.providers.catbox import upload_bytes

        out: dict[int, str] = {}
        for entry in entries:
            if entry.anilist_id is None:
                continue
            sel = await self.cache.get_selection(code, entry.index)
            url = sel.thumbnail_url if sel else None
            if not url or not url.startswith("file://"):
                continue
            path = Path(url[len("file://"):])
            try:
                data = path.read_bytes()
                public = await upload_bytes(data, filename=f"thumb_{entry.index}.jpg")
                out[entry.anilist_id] = public
            except Exception as exc:  # noqa: BLE001 — a missing render just falls back
                log.warning("senku.publish.thumb_bridge_failed",
                            code=code, entry=entry.index, error=str(exc))
        return out

    async def _cache_image(self, image) -> str | None:
        """Push a card image URL through catbox (matching the bot's read path).

        ``image`` may be a URL string, a ``Path``, or ``None``. A ``file://`` /
        local path is uploaded as bytes; a remote URL is cached via catbox's
        URL uploader; ``None`` passes through. On any failure the original
        string is returned so a single broken cache never drops the image.
        """
        if not image:
            return None
        image_str = str(image)
        try:
            if image_str.startswith("file://") or Path(image_str).exists():
                from nekofetch.providers.catbox import upload_bytes

                raw = Path(image_str[len("file://"):] if image_str.startswith("file://")
                           else image_str).read_bytes()
                cached = await upload_bytes(raw, filename="card.jpg")
                return cached or image_str
            if self._c.config.features.catbox_image_cache:
                from nekofetch.providers.catbox import upload_from_url

                cached = await upload_from_url(image_str)
                return cached or image_str
        except Exception as exc:  # noqa: BLE001 — caching is best-effort
            log.debug("senku.publish.image_cache_failed", url=image_str, error=str(exc))
        return image_str

    # ── send ───────────────────────────────────────────────────────────────────

    async def _send_posts(
        self, client, chat_id: int, posts: list[dict],
    ) -> tuple[int, list[int]]:
        """Post every card into the channel, mirroring the distribution app.

        Divider sticker between sections, URL buttons from ``button_data``,
        ``{BOT_QUAL:...}`` placeholders resolved to the channel handle, and
        the info card + watch guide pinned (service notices swept). Returns
        ``(posted_count, pinned_message_ids)``.
        """
        import re

        fmt = self._c.config.post_format
        divider_id = fmt.divider_sticker_id or self._c.config.bot.divider_sticker_id
        posted = 0
        pinned_ids: list[int] = []

        # Resolve a public handle for {BOT_QUAL} links. In a channel these point
        # at the channel itself (deep-linking to messages fails in private chat).
        try:
            chat = await client.get_chat(chat_id)
            handle = getattr(chat, "username", None)
        except Exception:  # noqa: BLE001
            handle = None

        for i, post in enumerate(posts):
            if i > 0 and divider_id:
                try:
                    await client.send_sticker(chat_id, divider_id)
                except Exception:  # noqa: BLE001 — divider is decorative
                    pass

            caption = post.get("caption") or ""
            if caption:
                if handle:
                    caption = re.sub(
                        r"\{BOT_QUAL:([^}]+)\}",
                        rf'<a href="https://t.me/{handle}">\1</a>',
                        caption,
                    )
                else:
                    caption = re.sub(r"\{BOT_QUAL:([^}]+)\}", r"\1", caption)
                caption = resolve_premium_emoji(caption, fmt)

            markup = build_audio_keyboard(post.get("button_data"), fmt)
            image = post.get("image")
            try:
                if image:
                    msg = await client.send_photo(
                        chat_id, image, caption=caption,
                        reply_markup=markup, parse_mode=ParseMode.HTML,
                    )
                else:
                    msg = await client.send_message(
                        chat_id, caption,
                        reply_markup=markup, parse_mode=ParseMode.HTML,
                    )
                posted += 1
            except Exception as exc:  # noqa: BLE001 — a partial channel still ships
                log.warning("senku.publish.post_failed",
                            post_type=post.get("post_type"), error=str(exc))
                continue

            if post.get("pinned"):
                await self._pin_silently(client, chat_id, msg.id)
                pinned_ids.append(msg.id)

        return posted, pinned_ids

    @staticmethod
    async def _pin_silently(client, chat_id: int, message_id: int) -> None:
        """Pin a message and sweep the "pinned this message" service notice.

        Mirrors :meth:`LogChannelService._pin_silently` — pin without a
        notification, then delete the auto-posted service notice so the channel
        stays clean. Every step is best-effort.
        """
        try:
            await client.pin_chat_message(chat_id, message_id, disable_notification=True)
        except Exception:  # noqa: BLE001
            return
        for candidate in range(message_id + 1, message_id + 4):
            try:
                msg = await client.get_messages(chat_id, candidate)
                if msg and getattr(msg, "pinned_message", None) is not None:
                    await client.delete_messages(chat_id, candidate)
            except Exception:  # noqa: BLE001 — sweep is best-effort
                pass
