# Gojo Bot — Full Build Plan

Gojo is the **publisher**: the final relay stage. Senku finishes the distribution
channel → hands off to a Gojo admin → Gojo builds & posts the main-channel entry,
indexes it, and owns the long-lived maintenance jobs (monthly updates, banned-channel
recovery, universal footer edits, and full backup/restore of everything it posts).

This plan is grouped into phases. Each phase is independently shippable and tested.

---

## What already exists (reused, not rebuilt)

- `MainChannelService` — gathers facts, builds caption, posts to main channel, tracks `ChannelPost`.
- `IndexChannelService` — dynamic A–Z index with overflow shifting; already seeded.
- `UpdateCheckService` — walks franchise, finds new TV/extra entries, creates requests. **Has a latent bug** (`security.owner_ids` — config only has `owner_id`).
- `StatsService` — computes catalog stats.
- `BotOrchestratorService.recreate_bot` — banned-channel recovery.
- `catbox.upload_bytes` / `upload_from_url` — image host.
- `TelegraphClient` — gallery creation (not file upload).
- `Scheduler` (APScheduler) — `every()` / `at()`.
- `handoff_distribution_to_publish` — DMs Gojo admins when a title is ready.
- `ThumbnailChannelService` / Senku thumbnail adapter — logo/poster/backdrop selection.

## Latent bugs to fix along the way
1. **Gojo duplicate `/settings`** — `handlers/tasks.py:159` still defines an old `/settings` that fights the shared settings engine. Remove it.
2. **`UpdateCheckService` `owner_ids`** — reads `self._c.config.security.owner_ids` (doesn't exist). Fix to `owner_id`.
3. **Main-channel episode count** — currently `max(episode_to/file_count)`; must become **sum of TV-season episode counts only** (extras excluded).

---

## Phase 1 — Gojo voice + task-driven publish flow

**New:** `shared/gojo_voice.py` (mirrors `senku_voice.py`/`levi_voice.py`): persona strings, card copy, button labels. Gojo = 🔮, "The Strongest Sorcerer".

**Handoff → task:** keep the one-tap entry, but the review card gets buttons:
- 🚀 **Publish Now**
- 🔕 **Silent Publish** (post with `disable_notification=True`)
- 📅 **Schedule** (pick a time → APScheduler `at()` fires the publish)
- ✏️ **Edit Caption** (existing)
- ❌ Cancel

Rework `bots/gojo/handlers/tasks.py` review flow to render via `gojo_voice` + `send_screen` (image cards, not bare text replies), consistent with the other bots. Remove the dead `/settings`.

**Tests:** publish/silent/schedule routing; caption edit still applies; scheduled job registers.

---

## Phase 2 — Correct main-channel post content

In `MainChannelService.gather_facts`:
- **Episodes** = Σ episodes of **TV seasons only** (from franchise walk / TV packs), not the base entry, not extras.
- **Synopsis/overview** = TMDB (franchise-level), replacing AniList's base-entry synopsis. Already prefers TMDB; make it authoritative for the main post and strip to a clean single paragraph (collapse hard line breaks, keep it readable).
- **AniList rating** = **average of all franchise entries' scores** (`FranchiseEntry.score`), not the base entry. New helper to walk the franchise and average non-null scores.
- **Thumbnail** = first-TV-entry (season 1) generated thumbnail (already the rule). TMDB rating stays baked in the thumbnail image (unchanged).

**Tests:** episode-sum excludes extras; franchise rating average; TMDB synopsis wins; season-1 thumbnail chosen.

---

## Phase 3 — Manual asset upload (logo/poster/backdrop)

Both in the **thumbnail channel service** and the **Senku thumbnail wizard**, add an
**"⬆️ Upload my own"** button next to the numbered TMDB options for each asset type.
Flow: tap → FSM waits for a photo/document → on receipt, upload the image bytes to the
image host (Phase 5 backup helper) → store that URL as the entry's `logo_url`/`poster_url`/`bg_url`
exactly as a TMDB pick would. Everything downstream (render) is unchanged.

**Tests:** upload sets the right asset URL; render proceeds; falls back cleanly if upload fails.

---

## Phase 4 — Index correctness + universal footer edit

**Index bullet fix:** the empty index cards already contain a bullet. When adding the
first title to a letter, emit **`{title}`** (no leading bullet) if the section template/existing
content already starts with the bullet — never `⦿ ⦿ name`. Audit `IndexChannelService`
caption rendering + `index_channel.entry_template` and de-dupe the bullet.

**Universal footer edit (new Gojo feature):** a Gojo action "✏️ Edit Footer (all channels)".
Admin sends new footer text (Telegram entities / Markdown / HTML — reuse
`shared/settings_ui.parse_user_markup`). Gojo iterates every `DistributionBot` row
(channels + bots it can reach), finds the footer message (image-with-caption) in each,
and **edits its caption** universally. Footer message id must be tracked — see Phase 5
(persist `footer_message_id` per channel).

**Tests:** bullet not doubled; footer edit updates caption across mocked channels; styling parsed.

---

## Phase 5 — Backup & restore (the big one)

**New model** `PublishedPostBackup` (Postgres): everything needed to rebuild a post byte-for-byte:
- `anime_doc_id`, scope (main / distribution / index)
- `caption` (raw HTML, styling preserved), `button_data` (JSON), `image_url` (hosted), `image_source` ("catbox"/"telegraph"/"envs"), `post_type`, `order`, `pinned`, `divider_before` (bool)
- for distribution channels: the full ordered card list (info → seasons → extras → guide → divider → footer), each with its own row.
- `footer_message_id` per channel (for Phase 4 edits + footer-update flow).

**New:** `shared/image_backup.py` — `host_image(bytes|url) -> (url, source)` with fallback chain:
1. **catbox** (`upload_bytes`) — primary.
2. **Telegraph** `uploadFile` (add `TelegraphClient.upload_file`) — 2nd.
3. **envs.sh** (already used in config) — 3rd.
Returns the first success + which host, so the DB records where it lives. Every image Gojo/Senku posts is run through this and recorded.

**New:** `BackupService`:
- `record_main_post(...)`, `record_distribution_channel(...)`, `record_index(...)` — called at post/publish time.
- `restore_main_channel(new_channel_id, *, mode)` — re-post all saved main-channel entries to a new channel id. Modes: **all at once**, **N per day**, **every X minutes** (APScheduler). Progress + resume.
- `restore_distribution_channel(code, new_chat_id)` — re-post the saved card list verbatim (captions, buttons, dividers, footer, pins) — **no regeneration, no re-render** (thumbnails already hosted).

**Wire into recovery:** `BotOrchestratorService.recreate_bot` (banned distribution channel) → after Senku admin creates the replacement channel, call `restore_distribution_channel` instead of regenerating.

**Main-channel migration:** a Gojo action "🆕 Change Main Channel" — set new channel id → choose send mode → `restore_main_channel` streams every saved post to it.

**Tests:** host_image fallback order (catbox fail → telegraph → envs); backup round-trips caption+buttons+styling; restore posts in order with dividers/pins; paced restore schedules correctly.

---

## Phase 6 — Monthly maintenance (updates + ban check) with edit-before-submit

**Update check (channel update, not main-channel repost):**
- Fix `owner_ids` bug. Run `UpdateCheckService.check_all` monthly (APScheduler) **and** via a Gojo "🔁 Check Updates" button.
- Result → DM a Gojo admin a **list** with an **✏️ Edit** button. Editing shows the list as copyable text; admin removes/adds entries (instructed to use official AniList names for adds). On submit, each entry becomes an auto-request → normal pipeline (Levi → Senku thumbnail for **that entry only**).
- **These do NOT post to main channel.** They **update the distribution channel**: delete the **footer message only** (image-with-caption; divider stays), append the new entry's card(s), then a new divider + new footer. New `update_distribution_channel(code, new_entries)` on the publisher path.

**Ban check:**
- Monthly + manual "🛡 Check Banned". For each `DistributionBot`, probe reachability. On ban → send a **channel-creation request to Senku** admins; once recreated, `restore_distribution_channel` (Phase 5) reposts from backup (no re-render).
- Main channel ban is handled by Phase 5 "Change Main Channel".

**Tests:** update list edit add/remove; entry-only thumbnail path; footer-swap update ordering; ban probe triggers Senku request; monthly jobs registered.

---

## Phase 7 — Stats + settings polish

- Gojo "📊 Stats" screen via `StatsService` + backup counts: posts saved, files in DB added by our bots, channels tracked, last update-check/ban-check timestamps, scheduled restores in flight.
- Ensure Gojo's settings (already on the shared human-friendly engine: `main_channel`, `index_channel`, `thumbnail_channel`) include footer text + new backup/schedule prefs. Add config keys as needed (e.g. `main_channel.silent_default`, restore pacing defaults).

**Tests:** stats compute; settings render.

---

## Config / schema additions
- `security.owner_id` stays; fix the service. (Consider `owner_ids` property returning `[owner_id] + admin_ids` for compatibility.)
- New: image-host fallback order, restore pacing defaults, monthly-job enable flags, footer message tracking.
- Document every new key in `settings_schema.py` (human-friendly, per the last session's UX rules).

## Cross-cutting
- All new admin surfaces use `send_screen` + artwork + `gojo_voice` (no bare text, no orphan images — the `send_screen` overflow fix already landed).
- All input parsing reuses `settings_ui.parse_user_markup` (Telegram/HTML/Markdown + real newlines).
- Migrations: one Alembic revision for `PublishedPostBackup` + `footer_message_id`.
- Commit + push at the end of each phase (per standing rule), full suite green each time.

## Sequencing
Phase 1 → 2 → 3 → 4 → 5 → 6 → 7. Phases 5 and 6 are the largest; 1–4 are quick wins that also fix the latent bugs. I'll checkpoint with you after Phase 2 (visible main-channel change) before the heavy backup/maintenance work.
