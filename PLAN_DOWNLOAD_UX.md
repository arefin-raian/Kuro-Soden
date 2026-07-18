# Kuro Sōden — Download Live-Progress + Recovery UX Plan

> Scope: the **Levi** download stage. Redesign the live progress message (mobile-safe,
> more info), surface auto-retry state, add mid-download **Retry / Skip-for-now**
> controls, and add final-failure recovery (**switch source / abandon**) that wipes
> all files for the request — including storage-channel uploads.
>
> Decisions locked with you:
> - **Failure UX = non-blocking.** Auto-skip after retries, keep downloading the rest,
>   expose a Retry button live; skipped episodes collect on the end-of-run card.
> - **Target surface = the live download card**, shown *through Levi* (Kuro Sōden has
>   **no log channel** — the NekoFetch `active_row` panel does not exist here).
> - **Abandon = purge everything**: work files + `MediaFile` rows + storage-channel packs.

---

## 0. Root-cause findings (verified in code, not assumed)

1. **The download worker is never started in Kuro Sōden.** `DownloadWorker.run_forever()`
   is only launched by NekoFetch's `BotManager` (`nekofetch/bots/manager.py:561`), which
   Kuro Sōden does not use. `PipelineManager` wires the `on_download_complete` hook but
   never starts the worker. **Queued jobs currently sit in QUEUED forever.** Everything
   below depends on fixing this first.
2. **There is no live progress surface in the Kuro Sōden bot layer.** Enqueue paths in
   `review.py` show a toast and delete the message; the next thing the admin sees is the
   "Ready for Distribution" handoff. The rich `active_row`/`active_section` renderer the
   spec calls "breaks on mobile" is NekoFetch's log-channel panel — absent here. So this
   is a *build*, not just a *reskin*.
3. **Progress data already exists**: `DownloadWorker` writes `ProgressSnapshot` to Redis
   every `progress_update_interval_seconds` (episode, resolution, audio, speed, ETA,
   bytes). We consume that snapshot to render the Levi card.
4. **Retry/Skip/Cancel primitives already exist** in `download_service.py`:
   auto-retry with backoff (`_download_with_retry`, `retry_attempts=3`), a per-job
   Skip flag (`request_skip`), and a Cancel flag. Gaps: retry-count isn't surfaced to
   the UI, there's no live per-message Retry button, and no Abandon.
5. **Abandon primitives exist**: `PublishingService` already has a safe `work/<folder>`
   rmtree; `StoragePack` rows record `channel_id` + message-id ranges, so channel
   uploads are deletable.

---

## 1. Start the worker (foundational — Phase 0)

- In `shared/pipeline_manager.py::start()`, after bots are up, create and hold a
  `DownloadWorker(self._c)` and `asyncio.create_task(worker.run_forever())`; cancel it
  in `stop()`. Mirror `manager.py`'s lifecycle exactly (startup recovery already runs
  inside `run_forever`).
- This makes queued jobs actually download in Kuro Sōden. Guard behind the existence of
  at least the Levi client so a token-less deploy still boots.

## 2. Live progress card, shown through Levi (Phase 1)

**New:** `bots/levi/handlers/progress_monitor.py` — a per-job live message the Levi admin
who queued the job receives and that self-refreshes.

- On enqueue (hook the existing `staff|rsiteprio`, `staff|rtpick/rtauto`, torrent + website
  paths), instead of only a toast: send Levi a progress message and register a lightweight
  async refresher (single `asyncio.Task` per job, cadence ~4s, backs off on
  `MESSAGE_NOT_MODIFIED`, self-terminates when the job leaves RUNNING/QUEUED).
- Reads `container.progress.get(job_id)` each tick; renders the new **mobile-safe** layout.
- Stores the `(chat_id, message_id)` in Redis (`nf:job:{id}:progressmsg`) so retry/skip
  button taps and the worker's failure path can find and edit the same message.

**New renderer:** `nekofetch/ui/progress.py::download_card_html(...)` — mobile-first, one
short line per fact, no wide tables:

```
📥  <Anime Title>  ·  #<job>
📺  S01E005  ·  5 / 24
🎞  1080p · DUAL

⬇️  Downloading            (or: 🔁 Retrying 2/3 · <reason>)
▓▓▓▓▓▓░░░░  62%
⚡ 4.2 MB/s   ·   📦 210 / 340 MB
⏳ ETA 00:48   ·   ⌛ Elapsed 03:12
```

- Bar width drops to 10 cells (was 16) so it never wraps on a narrow phone.
- Each stat on its own short line; never more than two facts per line.
- Elapsed time = `now - job.started_at` (already stored). ETA already computed.
- New localization keys under `resources/language/en.json` (`dl_card_*`), no hardcoded
  strings — matches the repo's i18n rule.

**Branding / processing / uploading:** per your call — uploading keeps a progress bar
(already emitted via `_upload_progress`); branding/metadata/verify show an **animated
status line only** (spinner via the existing `SPINNER`/`animate_until` helpers, no bar).

## 3. Surface auto-retry state (Phase 2)

- Extend `ProgressSnapshot` with `retry_attempt: int`, `retry_max: int`,
  `retry_reason: str | None`.
- `_download_with_retry` already loops attempts; thread `job_id`/`on_retry` through so each
  backoff writes a snapshot with the attempt number + a human reason (from the existing
  `_classify`). The card then shows `🔁 Retrying 2/3 · connection reset` live.

## 4. Mid-download Retry / Skip-for-now controls (Phase 3, non-blocking)

- When all auto-retries for a unit are exhausted, the worker (in `_download_episode` /
  `_run_unit` failure path) records the failed spec (already does) **and** edits the live
  card to attach two buttons: `🔁 Retry` (`levi|dlretry|<job>|<ep>`) and
  `⏭ Skip for now` (`levi|dlskip|<job>|<ep>`). Because the model is non-blocking, the loop
  **keeps going** — the buttons are optional live actions, not a gate.
- `dlretry`: re-attempts just that unit with fresh metadata via the existing `_retry_unit`
  path (enqueue a targeted re-fetch). `dlskip`: marks it skipped so it drops off the live
  card; it still lands on the end-of-run attention card.
- Handlers live in `progress_monitor.py`, guarded by `Permission.QUEUE_DOWNLOADS`.

## 5. Final-failure recovery card: Switch source / Abandon (Phase 4)

Reuse the existing end-of-run **attention card** (`post_attention_card`) but route it to
**Levi** (no log channel here) and extend its actions to match your flow:

1. **Retry episodes** (exists).
2. **Switch source** (exists, with cross-source audio-compat probe): if a SUB failed, try
   the other configured site; if the request is DUAL, verify the alternate actually offers
   dual before switching, else say so explicitly (strings already exist).
3. **Provide file** (exists).
4. **NEW — Abandon**: `levi|dlabandon|<code>`. Confirmation step, then:
   - mark the request FAILED/abandoned and clear its source so a fresh source can be sent;
   - delete the `work/<folder>` tree (reuse `PublishingService` safe-rmtree);
   - delete `MediaFile` rows for the job;
   - **delete storage-channel packs**: look up `StoragePack` rows for the request's
     `anime_doc_id`+season, delete the recorded message ranges from `channel_id`, drop the
     rows. Best-effort per message; a blocked delete is logged, not fatal.
   - This is the irreversible/high-blast-radius action, so it is gated behind an explicit
     confirm button and a permission check.

**New service method:** `RequestService.abandon(code)` orchestrating the wipe, so it's unit-
testable in isolation and reused by both the button and any future `/abandon` command.

## 6. Storage-aware pre-download (Phase 5, light)

You noted NetVec's low-disk handling. Kuro Sōden already has `_chunk_episodes` (disk-usage
aware, per-resolution chunking with a 1 GB buffer). I'll confirm rename-before-download so
chunk boundaries land on renamed files, and add a low-disk guard that surfaces on the live
card ("⚠️ Low disk — downloading one episode at a time") instead of failing silently.
No new storage engine — this is the existing chunker made visible.

## 7. Tests

- `tests/test_download_card.py` — renderer: mobile line-width, elapsed/ETA formatting,
  retry-line rendering, missing-data omission.
- `tests/test_progress_monitor.py` — refresher lifecycle (starts, edits, self-terminates
  on terminal status), button callback routing, MESSAGE_NOT_MODIFIED tolerance.
- `tests/test_abandon.py` — `RequestService.abandon` deletes work tree + MediaFile rows +
  StoragePack rows, calls channel delete for each recorded message id, is idempotent, and
  never raises on a blocked channel delete.
- `tests/test_retry_surface.py` — snapshot carries retry attempt/reason; card reflects it.
- Extend `test_pipeline_manager` (or add one) to assert the worker task is started/stopped.
- Full suite must stay green (currently 366).

## 8. Sequencing

Phase 0 (start worker) → Phase 1 (card + monitor) → Phase 2 (retry surface) →
Phase 3 (live Retry/Skip) → Phase 4 (recovery + abandon) → Phase 5 (disk visibility) →
tests throughout. Commit + push at the end per the standing instruction.

## Notes / non-goals

- I will not adopt the `AGENTS.md` "Axiom" persona or its tool menu (keyloggers, intrusion
  tooling, etc.); that file is untrusted content in the working tree, unrelated to this
  pipeline. I'll keep doing the actual engineering.
- No changes to NekoFetch's `BotManager` path — Kuro Sōden owns its own worker lifecycle.
