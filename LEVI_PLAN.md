# Levi (Downloader Bot) — Native Flow & UI Overhaul

Kuro Sōden's second bot. Today Levi is a thin menu that **borrows NekoFetch's admin
`review.py`** wholesale (`staff|`/`franchise|`/`anizone|` callbacks). We replace that
with a **native `levi|` flow** that owns its own UI, voice, backdrop-cycling cards, and
live-toggle keyboards — consistent with Lelouch, but distinctly Kuro Sōden.

## What already exists (reuse, don't rebuild)

- **Sources** (`nekofetch/sources/`): `kickassanime.py`, `anikoto.py`, `anizone.py`,
  `nyaa.py` (torrents), `local.py`, `_torrentdl.py` (aria2 fast DL, folder-aware),
  `_torrent.py`. All implement the `AnimeSource` ABC → `search / get_episodes /
  get_variants / coverage() → SourceCoverage`. **Fully implemented.**
- **aCute provider** (`nekofetch/providers/acute_bot.py` + `sources/telegram/userbot.py`
  `UserbotPool`): userbot `/anime` probe → menu tap → info card → AniList-ID verify.
  Reads `TELEGRAM_USERBOT_SESSION`. Built; just needs the env field + session string.
- **Franchise resolver** (`shared/franchise_resolver.py`): `resolve_franchise()` chain
  AniList → Jikan(fused in `container.anilist`) → aCute → TMDB → canonical franchise dict.
- **Artwork/backdrop cycling** (`nekofetch/ui/artwork.py`): `ensure_anime_art(key,…)` +
  `next_anime_art(key, fallback_bot="levi")` — per-anime backdrop rotation, no back-to-back
  repeat, shared across all 4 bots in one process. `pick_artwork("levi")` for generic art.
- **Card builder** (`nekofetch/ui/components.py` `cb()`/`parse_cb()`; screens `card(...)`).
- **Config scaffolding** (`nekofetch/core/config.py`): `DownloadsConfig`, `ProcessingConfig`,
  `RenameConfig` (template + movie/special templates), `BrandingConfig`, `WatermarkConfig`,
  `MetadataConfig`, `ThumbnailConfig`, `StorageChannelConfig` (header templates).
- **Work queue**: `shared/work_service.py` (`WorkItem`), `shared/admin_assignment.py`
  (`AdminAssignmentEngine.get_active_tasks`), `shared/pipeline_manager.py`.
- **Reports**: `nekofetch/services/website_report.py`, `nekofetch/ui/website_report.py`.

## Decisions (locked with user)

1. **aCute session**: user pastes their own `StringSession`. We only add the
   `TELEGRAM_USERBOT_SESSION` field to `.env.example` + `EnvSettings` and consume it.
2. **Delivery**: one commit per phase, **single push at the very end**.
3. **Old flow**: **replace** — build native `levi|`, then unmount `review.register` from
   Levi once the native flow reaches parity. No duplicate machinery.

## Cross-cutting (applies to ALL FOUR bots)

- **Live-toggle keyboards**: option/toggle buttons (franchise-map select, resolution
  picks, on/off) MUST update via `q.message.edit_reply_markup(new_markup)` — never
  delete+resend. Add a shared helper `edit_markup(q, buttons)` in `nekofetch/ui/components.py`
  and refactor the existing toggle sites in Lelouch/Levi to use it. Content changes
  (new screen/image) still use `send_screen(old_msg=…)`; only **keyboard-only** changes edit
  in place.
- **Backdrop on every card**: every non-trivial card gets a cycled anime backdrop via
  `next_anime_art(key)`; small confirm/prompt messages stay imageless.
- **Voice**: add `shared/levi_voice.py` mirroring `lelouch_voice.py` — Levi Ackerman's terse,
  disciplined tone.

## Phases

### Phase 0 — Foundation: env, voice, live-toggle helper, settings audit
- Add `TELEGRAM_USERBOT_SESSION` (+ document `TELEGRAM_USERBOT_ACCOUNTS[_FILE]`) to
  `.env.example` and `EnvSettings`.
- `shared/levi_voice.py` (Levi persona lines).
- `edit_markup(q, buttons)` helper + refactor existing Lelouch toggle to use it.
- **Fix Levi settings panel**: full `/settings` hub covering downloads, processing, rename
  (template/movie/special + variable legend & examples), branding, watermark, thumbnail,
  metadata. Model the well-documented `settings_content.py` section shape; add missing keys.
- Tests: `test_levi_settings.py` (every documented key maps to a real config field),
  `test_edit_markup.py`, env-field load test. **Commit.**

### Phase 1 — Native request card + franchise-map selection
- `bots/levi/screens.py`: `request_card(work_item)` → backdrop + caption (Levi voice) +
  two buttons: `levi|report|<code>` (Generate Report) and `levi|assign|<code>` (Assign
  Source Directly).
- Franchise-map selection screen (shared, since both paths need it):
  `franchise_select(mapping, selected)` — one toggle row per entry (title from AniList:
  "Attack on Titan S2", movies, OVAs), default all selected, `✓/☐` glyphs, **live
  `edit_markup`** on toggle, "Select all / none", Continue. Backed by FSM state in the
  `levi` namespace.
- Jikan + aCute franchise-map parity: ensure `resolve_franchise` fills the franchise
  breakdown (canon + summary movies/specials, drop filler recaps) for all three providers,
  not just AniList. Verify in resolver adapters.
- Tests: `test_levi_request_card.py`, `test_franchise_select_toggle.py` (toggle flips
  state + edits markup, not resend), `test_franchise_parity.py`. **Commit.**

### Phase 2 — Source report (Generate Report path)
- `bots/levi/report.py` (or reuse/extend `services/website_report.py`): build per-source
  report over the **selected** franchise entries, new backdrop image.
  - **Telegram**: fixed manual note (search hint, ≥3-resolution rule, screenshot-bot
    mediainfo + watermark/metadata check, embedded-watermark → reject).
  - **KickAss / AniKoto**: `coverage(*titles)` → matched N/total, per-entry sub/dub/dual,
    audio/subtitle tracks, duration/multi-audio notes (AniKoto sub≠dub duration).
  - **Torrent (Nyaa)**: top-5, dual-audio flag, seeders/leechers, size.
  - **AniZone**: search-result listing (regular + special counts) + **expandable block-code
    warning** "not recommended (ambiguous)".
  - **Suggestion** line: recommended source + why.
- Source-pick screen after report (or directly via `levi|assign`): Telegram / KickAss /
  AniKoto / AniZone / Torrent / **DDL** buttons — single source, no fallback chain.
- Tests: `test_levi_report.py` (each source section renders from a faked `SourceCoverage`;
  AniZone warning present; suggestion computed), with sources mocked. **Commit.**

### Phase 3 — DDL + download engine + packs (folders)
- **DDL source** `nekofetch/sources/ddl.py`: accept a direct link (zip/compressed or file),
  download via aria2 (port `_torrentdl.py` patterns: multi-connection, folder-aware,
  sequential per-file for folder DDLs), extract (`7z`/`shutil`) into per-entry **pack
  folders**, walk tree for media. Season/episode parse ported from Leech-main
  `leech_utils.extract_metadata_from_filename` (custom regex; season fallback → S1).
- Download orchestration per selected source: create folder per pack/entry, keep separate.
  **AniZone**: single-title search, separate `regular/` vs `special/` folders, then manual
  "this pack = <AniList title>" mapping step (connect-the-dots).
- Torrent folder handling: research nested-folder torrents (anytree-style walk) → packs.
- Live progress via `edit_markup`/caption edits (no resend spam).
- Tests: `test_ddl_download.py` (mock aria2 + a fixture zip with nested folders → correct
  packs), `test_filename_parse.py` (season/episode/movie/special cases, S1 fallback),
  `test_anizone_pack_split.py`. **Commit.**

### Phase 4 — Rename, branding, media-info verify
- **Short-title step first**: if title > 3 words → offer acronym (stopword-excluded), or
  ask for short name, or pick from AniList/Jikan alt titles. Store per-job.
- **Rename**: show default title + `RenameConfig` template; ask "default for all packs / just
  this / mark type per pack". Per-type templates (season/movie/special) like NekoFetch;
  unparseable season → S1.
- **Brand** files (`BrandingConfig`).
- **Media-info verify**: per-pack message with a "Media Info" button → telegraph-style page
  (mediainfo/ffprobe). User confirms or corrects (dual→multi, wrong season) → re-rename the
  whole pack (all resolutions).
- Tests: `test_short_title.py` (acronym rules, >3-word threshold, stopwords),
  `test_rename.py` (per-type templates, offset tokens, S1 fallback),
  `test_mediainfo_render.py`. **Commit.**

### Phase 5 — Thumbnail, caption/header, DB upload, handoff
- **Thumbnail** step: ask for image, instruct 1:1 crop; no artwork on these simple prompts.
- **Header/caption** step: show `StorageChannelConfig.header_template`, offer edit with
  variable legend, live-update the preview, confirm.
- **Upload** packs → DB (`StoragePack`/`MediaFile`), mark `WorkItem` stage → next
  (distribution). If more assigned tasks → present next request card immediately.
- **Unmount** `review.register` from `bots/levi/handlers/__init__.py`; delete the borrowed
  wiring. Keep `staff|` review only where NekoFetch/other bots still need it.
- Tests: `test_levi_handoff.py` (pack persisted, stage advanced, next task surfaced),
  `test_levi_no_review_mount.py` (routing test à la `test_lelouch_routing.py`: every `levi|`
  callback a Levi screen emits has a handler; no dead taps; review flow no longer mounted).
  **Commit.**

### Phase 6 — Full-suite verify + final push
- Run the entire suite; fix regressions. Ensure no `staff|` dead taps remain on Levi.
- `clear_database.py` still green.
- **Single `git push`** of all phase commits to `main`.

## Test strategy

- Offline: build the Levi client with a `FakeContainer` (as in `test_lelouch_routing.py`),
  drain deferred registration, invoke real filters against synthetic `CallbackQuery`.
- Mock all network sources (`container.sources.get(...)` returns fakes yielding
  `SourceCoverage`/`Episode`/`VideoVariant`); mock aria2 subprocess for DDL/torrent.
- Routing/dead-tap guard for Levi mirroring the Lelouch test.
- No live Telegram, no live scraping in tests.

## Risks / notes

- aCute won't run non-interactively until you paste `TELEGRAM_USERBOT_SESSION`; flow
  degrades gracefully to AniList/Jikan/TMDB until then.
- `work_items` table is registered in ORM but **not migrated** in the live `kage` DB
  (surfaced by `clear_database.py`). Levi writes work-items → must apply the migration
  first (`20260718_0010_add_work_items.py`). Included in Phase 0.
- Live-toggle refactor touches all 4 bots; done incrementally with tests to avoid
  callback regressions.
