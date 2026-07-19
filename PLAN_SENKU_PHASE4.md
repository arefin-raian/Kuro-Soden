# Senku Phase 4 — watch-order confirm + channel posting (preview-grammar) + Gojo handoff

## The insight
`scripts/preview_distribution_bot.py` is the exact post grammar we want in the real
channels. Its weak fallbacks (`--no-acutebot`, its own `_gather_metadata`) live **only in
the script**. The production card builders it calls —
`BotContentService._build_info_card`, `_build_season_card`, `_build_season_buttons`,
`_build_franchise_watch_guide` — already use the robust acutebot → AniList → TMDB chain.

So Phase 4 = reuse those production builders + replicate the preview's *posting choreography*
(info card → dividers → season/extra cards → divider → pinned watch guide → divider → footer,
then pin info + guide and sweep pin-notices) into the real Senku-admin'd channel, with **our
Phase 3 thumbnails swapped in for AniList banners**.

## What changes vs the preview
- **Images**: instead of `entry.banner_url or entry.cover_url`, each card prefers the
  Phase-3 rendered thumbnail for that entry, keyed by `anilist_id`, falling back to
  AniList banner → poster → cover (the preview's own order). Our renders are `file://`
  paths in `DistributionCache`; we upload them to catbox first (via `providers/catbox.py`)
  so Telegram can post a public URL.
- **Real channel, real client**: post via Senku's live Pyrogram `client` to the cached
  `chat_id` (Senku is already an admin from Phase 2). `_broadcast_to_channel` bails when
  `container.admin_client` is None (it is None here), so we post ourselves — this also lets
  us do dividers + pin + notice-sweep, which `_broadcast_to_channel` doesn't.
- **Watch order**: driven by the confirmed/edited cached entry list, not a fresh AniList walk.

## Files

### 1. `shared/senku_posting.py` (new) — the poster
`SenkuChannelPublisher(container)` with one public coroutine `publish(client, code) -> bool`:
1. Load franchise + entries + selections + channel(`chat_id`) from `DistributionCache`.
2. **Bridge thumbnails**: for each entry with a rendered `thumbnail_url` (`file://…`),
   upload bytes to catbox → `{anilist_id: catbox_url}` map. Best-effort; a failed upload
   just falls back to AniList art for that card.
3. Build posts by reusing production `BotContentService` builders:
   - info card: `_build_info_card(meta)` where `meta` comes from `_gather_metadata` +
     franchise data already in cache.
   - season/extra cards: walk the **cached entries** (our confirmed order), build
     `entry_meta` (title/synopsis/thumbnail-image), call `_build_season_card` +
     `_build_season_buttons`. Buttons point at Gojo/placeholder like the preview.
   - watch guide: `_build_franchise_watch_guide(...)` (pinned).
   - footer: config footer text/image.
4. **Post choreography** (mirrors preview `_start`): info → for each card `_divider()` then
   send → divider → watch guide (capture id) → divider → footer. Track all msg ids.
5. **Pin** info card + watch guide (`pin_chat_message`, `disable_notification=True`), then
   **sweep pin-notices** using the canonical `stats_service` pattern (scan msg.id+1..+4,
   delete rows whose `pinned_message` is set). Divider sticker id from config
   (`ThumbnailChannelConfig.divider_sticker_id`, exposed in settings).
6. Return True on success. All steps best-effort/logged; a blocked single post never aborts.

Idempotency: publishing is manual (admin taps Publish); re-run reposts. We guard by
checking a Redis "published" flag on the code (set on success) and short-circuiting with a
friendly "already live" card — mirrors `add_to_queue`'s idempotency note in the plan.

### 2. `bots/senku/handlers/wizard.py` — wire Phase 4
Replace the `_enter_watch_order` stub's dead-end buttons with the real confirm card:
- Buttons: `✅ Order is correct` → `senku|wiz|post|<code>`; `✏️ Edit order` →
  `senku|wiz|oedit|<code>`.
- New router branches:
  - `oedit`: set FSM `STATE_AWAIT_ORDER`, send `V.WATCH_ORDER_EDIT_PROMPT` + copy-block
    (`franchise_map.render_copy_block`).
  - `post`: render `V.publishing(title)`, call `SenkuChannelPublisher.publish`, then on
    success render `V.published_done`, `cache.clear(code)`, `complete_task(code,"senku")`,
    `assign(code,"gojo")`, DM Gojo admins (reuse `handoff` DM pattern). On failure render
    `V.PUBLISH_FAIL` with a retry button.
- FSM text handler: extend the existing group-2 `_channel_text` (or add a sibling) to catch
  `STATE_AWAIT_ORDER`: parse via `FranchiseFlowService.parse_mapping_correction`; on success
  overwrite cached entries (`cache.set_entries`) and re-render the confirm card; on failure
  `V.watch_order_edit_failed()`.

### 3. `shared/handoff.py` — add `handoff_distribution_to_publish(container, code, title)`
Mirror `handoff_download_to_distribution`: complete `senku`, assign `gojo`, DM Gojo admins
with an "Open Publishing" button (`gojo|...`), rotating art. The wizard's `post` branch can
call this instead of inlining, keeping the handoff contract in one place.

### 4. Settings (light) — `shared/settings_content.py` / Senku settings
Expose divider sticker id + pin toggles + footer through the existing config-driven settings
hub so they're editable (no dead stubs). Keep minimal; reuse Levi's config-panel pattern.

## Tests — `tests/test_senku_posting.py` (new)
- info + season + watch cards built from cached entries (mock `BotContentService` builders).
- thumbnail bridge: `file://` selection → catbox upload called → url used as card image;
  upload failure falls back to AniList art.
- post choreography: dividers between cards, info + guide pinned, pin-notice sweep invoked
  (mock client records calls).
- on success: `cache.clear`, `complete_task`/`assign` fired, Gojo DM'd; idempotent re-run
  short-circuits.
- watch-order edit: `parse_mapping_correction` round-trip overwrites cached entries.
- Extend `test_senku_wizard_routing.py` WIZARD_CALLBACKS with `post` + `oedit`.

Full suite green (366+new). Syntax-check every touched file. Commit + push at the end.

## Open risks / notes
- Real outward posting to a live channel: gated behind the admin's explicit `✅/Publish` tap.
- `container.admin_client` is None, so we deliberately post via Senku's client (also needed
  for dividers/pins). We do **not** route through `_broadcast_to_channel`.
- Season buttons: preview uses placeholder callbacks; channels can't host callbacks. We post
  the cards with no reply_markup (or URL buttons) matching `_broadcast_to_channel`'s note.
