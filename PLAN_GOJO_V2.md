# Gojo V2 — finish 7 phases + settings redesign + per-admin timezones + durable scheduling

**Already fixed this session:** channel-broadcast handler moved off group 3 (owned by
`batch.py`, which would silently swallow text broadcasts) to group 13. Compiles; broadcast tests green.

**Audit result:** Phases **1, 2, 4** and the 3 latent bugs are DONE. Phases **3, 5, 6, 7** are
partial/missing. The human-friendly settings engine (`shared/settings_ui.py`) already exists and
Gojo uses it — the raw/ugly panel is the **old admin bot**. Scheduling is in-memory (lost on
restart), naive server-local, no per-admin timezone, no schedule table.

Decisions locked: full settings redesign · timezone for scheduling+display only (shifts stay UTC)
· one big delivery.

---

## A — Durable scheduling + per-admin timezone + anti-double-book
- **A1** Add `timezone: str|None` (IANA) to `AdminAvailability` + migration `0015`. NULL → global Asia/Dhaka.
- **A2** `timefmt.py` helpers: `tz_for(name)` (safe fallback), `parse_local(raw, tz)→UTC`, `to_tz(utc, tz)`. Storage stays UTC.
- **A3** New `ScheduledPost` model + migration: `request_code, anime_title, admin_telegram_id, scheduled_at (UTC), silent, caption_override, status, fired_at`. Mirrors the durable `ChannelBroadcast` pattern.
- **A4** `ScheduleService`: `schedule()`, `list_pending()` (all admins, ascending), `cancel()`, `sweep_due(client)` (60s scheduler job — publishes past-due rows via existing `_execute_publish`, marks published/failed; **this is what survives restarts**), `collision_window(when, ±10min)`.
- **A5** Rework Gojo Schedule flow (`tasks.py`): parse in admin's tz → UTC; show the **combined pending table across all admins in this admin's tz** when scheduling; warn on collision; after scheduling show the updated table. DB sweep is source of truth (in-memory `at` optional fast-path, idempotent).
- **A6** "🌍 My Timezone" per-admin picker in settings (common zones as buttons + type-an-IANA), writes to the admin's row.

## B — Settings full redesign (widgets + migrate old admin panel)
- **B1** Extend `FieldDoc` with `label` + `widget` (`toggle|text|number|list|template|choice|channel|sticker|timezone`); default inferred from type. Fill labels/widgets for slug-leaking / enum-as-freetext (`bot.avatar_source`) / raw-id / sticker fields.
- **B2** `settings_ui`: `choice`→tap buttons (kills typo-stores-garbage), `channel`/`sticker`→guided capture (raw still accepted), `template`→existing live preview, `field_label` prefers schema `label`.
- **B3** Migrate old admin panel (`nekofetch/bots/admin/handlers/settings.py`) onto `register_settings(...)` with owner-only gating — kills the 2× drift and raw presentation. Keep `/settings` + clear-overrides.

## C — Finish Phase 3 (manual asset upload)
- Add "⬆️ Upload my own" to the standalone `ThumbnailChannelService` asset pickers (wizard already has it); FSM waits for photo/doc → upload via `image_backup` → store as logo/poster/bg URL.
- Route wizard's `store_upload` through `image_backup` (mirror+fallback) instead of bare `catbox.upload_bytes`.

## D — Finish Phase 5 (backup & restore, distribution scope)
- Add **envs.sh** 3rd fallback in `shared/image_backup.py`.
- Extend backup to distribution channels + index: `scope` + ordered card-list storage + per-channel `footer_message_id` (migration). Add `record_distribution_channel`, `record_index`, `restore_distribution_channel` (verbatim, no re-render).
- **Wire capture at publish time** (`publishing_service.publish`/`main_channel_service`) so backups fill automatically.
- **Wire recovery**: `BotOrchestratorService.recreate_bot` → `restore_distribution_channel`.

## E — Finish Phase 6 (maintenance)
- Monthly **ban-check** APScheduler job (only manual today).
- Monthly update-check DMs a **reviewable list with Edit** instead of auto-creating (`create=False` on the scheduled path).
- Wire the **add-entries** edit path (`BTN_EDIT_LIST`/`UPDATES_EDIT_PROMPT` exist, no handler).

## F — Finish Phase 7 (stats + settings keys)
- Gojo "📊 Stats" screen via `StatsService` + backup counts + last update/ban-check timestamps + scheduled-posts-in-flight (uses A3).
- Add settings keys: `main_channel.silent_default`, restore pacing, image-host order, monthly-job flags — with schema labels/widgets from B.

## G — Verification
- Unit tests per workstream: tz round-trip (parse_local/to_tz), ScheduleService sweep + collision + combined-table conversion, migration head singular, choice/channel/sticker widget rendering, admin-panel-on-shared-engine, Phase 3 upload, distribution backup/restore round-trip, envs fallback order, Phase 6 review-not-autocreate + add-entry, stats compute.
- Full `pytest` green. `alembic upgrade head` single-head check. Byte-compile.
- One commit + push at the end (per standing rule), with the bundled pre-existing WIP noted.

## Sequencing
A → B → C → D → E → F, then G throughout. A and B are the largest and highest-value (your
explicit asks); C/D/E/F close the plan's gaps. Migrations chain from current head
`0014_add_channel_broadcasts`: `0015` (admin tz), `0016` (scheduled_posts), `0017` (backup scope).

## Risks / notes
- APScheduler in-memory jobs can't survive restart with closures — the DB sweep (A4) is the real fix; I won't rely on `scheduler.at` for durability.
- Migrating the admin panel (B3) touches a heavily-used surface; its tests must stay green, and owner-only sections must remain gated exactly as before.
- Per-admin tz deliberately does **not** touch `working_hours`/shift logic (your call), so the duty-rotation tests are untouched.
