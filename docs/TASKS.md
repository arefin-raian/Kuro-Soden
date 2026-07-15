# NekoFetch — Task Tracker

> Continuously updated. Mirrors the session task list.

## In Progress

- (none) — round 3 milestone complete (pre-rendered content + revision-aware
  redelivery; `require_approval_before_publish=false` by default).

## Pending (operator actions — need real credentials/infra)

- **Implement `scraper.py`** — operator fills the four `fetch_*` methods against an
  authorized source and sets `implemented = True` (see `docs/SCRAPER_GUIDE.md`).
- **Configure channels** — set `storage_channel`/`log_channel` ids, make the admin bot an
  admin of both, set the end-sticker file_id; then enable.
- **Run a live smoke test** — real Telegram API creds + Postgres/Mongo/Redis up
  (`docker compose up`), then exercise the request→download→publish→deliver loop.

## Pending (planned features — design decisions still required)

- **`/updates` new-season detector** — re-query AniList for already-owned titles, list
  finished (non-ongoing) seasons/movies/OVAs/specials not yet in storage with a
  paginated multi-select, then route selected entries through the existing source-
  assignment flow. Since bot content is DB-row based, the post-download step just
  regenerates `BotContentPost` rows for the affected bot — no live-message surgery
  needed. Needs caching/UX decisions for AniList rate-limit handling.
- **Custom-franchise manual mode (template not ready — on hold)** — for very
  long-running series (One Piece, Naruto Shippuden) where AniList's structure
  isn't ideal. Admin defines custom arcs/segments (`Naruto: Pain's Assault eps
  152–175`, `One Piece: Wano eps 892–1085`) that override the auto-generated
  structure. Routes through the same `franchise_data` JSONB that the batch
  handler builds. Design is parked until a real franchise is in front of us.

## Nice-to-have (future)

- Richer analytics windows (active-user time windows), staff-management UI, more languages.

## Completed

- Project scope, authorized-only policy, tech stack; reference repos analyzed.
- Documentation backbone.
- Foundation: package layout, config files, Docker, `.gitignore`, `.gitattributes`, `pyproject.toml`.
- Core: 3-layer config, logging, constants, exceptions, security (token cipher), DI container.
- Domain enums + permission model.
- Database: Postgres ORM schema, Mongo collections, Redis progress store, repositories.
- Authorized-source interface + `LocalFileSource`.
- Premium UX kit: progress bars, templates, i18n, components/pagination.
- Auth service + bot auth/rate-limit middleware.
- Multi-bot manager + admin bot welcome (staged animation).
- Service layer: request, queue, download worker (live progress + resume), processing
  pipeline (verify→rename→metadata→branding→thumbnail→store), branding engine,
  distribution (season packages, temp/protected links), analytics, settings, publishing.
- Admin bot: request flow, settings panel (live toggles), queue/analytics views, approval panel.
- Distribution bots: generation flow, live multi-bot add, anime-bot interface, season-package
  delivery with protected content + temporary links + auto-delete.
- Local git with logical conventional commits; clean compile of the whole `src` tree.
- GitHub: public repo created and `main` pushed to https://github.com/arefin-raian/NekoFetch.
- Metadata enrichment seam: isolated `providers/metadata/` (models, provider interface,
  single editable `scraper.py` placeholder, transformer, renderer), `EnrichmentService`
  (Mongo-cached), distribution-bot consumption with fallback, and `docs/SCRAPER_GUIDE.md`.
- Database (storage) channel: `StoragePack` model + `StorageChannelService` (assisted
  indexing + automated upload + range delivery), admin storage panel/indexing flow,
  distribution delivery via packs with fallback.
- Log channel: `LogChannelService` (all-event sink + two auto-updated pinned messages),
  scheduler refresh, instrumentation across services.
- Alembic migrations (async env + baseline) + `AUTO_CREATE_SCHEMA` toggle.
- Test suite (pytest) + GitHub Actions CI (ruff + compile + pytest).
- Force-subscribe gate, admin broadcast tool, per-bot title binding.
- Opt-in ffmpeg watermark processing stage.
- Staff & user management UI (promote/demote, ban/unban, approve) with audit logging.
- `docs/DEPLOYMENT.md` first-run + channel setup guide.
- Main + index channel publishing ([Index][Download], deep links, per-letter index posts).
- Multi-quality × language acquisition matrix (English subs enforced).
- Bot auto-branding on bind + pending-bot queue.
- Access/token system (trial + Linkvertise shortlink renewal) gating delivery; forward-to-saved hint.
- **Owner-priority queue band** — owner `AuthService.is_owner(user)` gets priority `10`
  on enqueue; everyone else gets `100`. FIFO within band; no worker changes (the
  existing `priority ASC, created_at ASC` ordering already gives the intended behavior).
- **Auto-publish on completion** — when `processing.require_approval_before_publish` is
  `false`, `download_service._complete()` runs `PublishingService.publish(code)` itself
  once the storage upload finishes. Logs failures but never marks the job failed.
- **`/batch` command** — staff+ comma-separated multi-request flow with paginated
  per-title version clarification and a final confirmation card. Reuses the
  `_media_to_franchise_dict` / `apply_franchise_totals` / `enrich_with_tmdb` helpers
  (now at module level in `requests.py`); each title wrapped in per-title try/except.
- **Pre-rendered distribution-bot content** — `BotContentService.generate_posts`
  now caches each post's card image to `storage_path/bot_cards/` at generate time
  (URL-hashed, atomic-rename, idempotent) and writes the local `Path` into
  `BotContentPost.image_local_path`. The distribution `/start` handler serves
  from disk via a `_is_cached_image` helper (which guards against zero-byte
  files that Telegram rejects) and falls back to `image_url` only when the
  cache row is missing or corrupt.
- **Revision-driven redelivery** — `DistributionBot.content_revision` (bumped in
  the same transaction as `generate_posts`) + new `bot_deliveries` table
  (per `(bot_id, user_id)`: chat_id, message_ids, pinned_message_id,
  delivered_revision). On `/start`, a returning user with stale delivery has
  their old watch-guide unpinned and prior messages deleted (chunked at
  Telegram's 100-id `delete_messages` cap) before the freshly-generated pack
  is re-delivered. Idempotent migration `0004_distribution_rev_delivery`.
- **`scripts/preview_distribution_bot.py`** — standalone preview script that
  drives `BotOrchestratorService.ensure_bot_for_anime` through the existing
  Pyrogram user session to create a real distribution bot end-to-end without
  downloading any media files. `/start` the result in Telegram to see exactly
  what end users see. Flags: `--anime`, `--dry-run`, `--no-cache`,
  `--no-main-channel`. Exits with safe codes on env errors / startup
  failures / AniList no-match; never destructive without user intent.
- **Catbox.moe-backed card-image cache** — `providers/catbox.py` (bytes-based
  upload; not `urlupload`, because TMDB/AniList CDNs block catbox's IP) +
  `BotContentPost.image_cached_url` column + `Features.catbox_image_cache`
  toggle. Distribution `/start` prefers `image_cached_url` over `image_url`;
  falls back gracefully on any catbox failure so a single broken poster
  never blocks the whole regeneration. Idempotent migration
  `0005_rename_to_cached_url` renames the previous `image_local_path` slot.
- **`processing.require_approval_before_publish` default = false** — pairs with
  the Session 4 auto-publish wiring so titles publish end-to-end after the
  storage upload with no admin click required by default.
