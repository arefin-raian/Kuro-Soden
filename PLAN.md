# Kuro Sōden — Lelouch (Request Bot) Rebuild Plan

> Scope: **Lelouch only** this round. Levi/Senku/Gojo untouched except where the
> pipeline contract forces a shared change (work-item table, handoff).
> Decisions locked with you:
> - **Work** = its own table, separate from **requests** (needs a migration).
> - **Everything at once**: intake + batch + force-join + full management system.
> - Force-join gates **requesting only** (browsing the bot is allowed).

---

## 0. Why it's broken right now (root cause, not symptoms)

1. **Dead callback routing.** `nekofetch/ui/screens.py::welcome()` emits buttons with
   callbacks `admin|home`, `queue|view|0`, `batch|new`, `staff|requests|0`, and a bare
   `home`. Lelouch's dispatcher only matches `^lelouch\|`. The reused NekoFetch handlers
   cover `^batch\|` and `^staff\|`, but **`admin|`, `queue|`, and bare `home` have no
   handler at all** → tap = nothing. That's the admin-panel-button-does-nothing bug.
2. **Two competing panels.** `/admin` and `/settings` are defined twice — once as inline
   command handlers in `app.py` (building `lelouch|…` panels) and once inside the
   `^lelouch\|` dispatcher. They drift; captions/artwork differ per entry path → the
   "come back and it looks different / blank" inconsistency.
3. **Thin cards.** Dedup card, admin-notify DM, and receipt hand-roll captions instead of
   going through one shared card grammar, so spacing/emoji/artwork are inconsistent and
   some surfaces show an image with no info (or text with no image).
4. **No voice.** Copy is generic ("Requests are paused"), not Lelouch.
5. Missing entirely: force-join gate, work-items, management system, batch left/right
   pagination confirm flow.

---

## 1. Design language — one card grammar, Lelouch's voice

Create `shared/lelouch_voice.py` (copy catalog) + extend `nekofetch/ui/screens.py` with a
single **`card()`** builder every Lelouch surface routes through:

- Header: `♟️ <b>Title</b>` inside a blockquote (matches `confirm_franchise`).
- Body: `<b>Label</b> : value` rows, expandable blockquote for long text.
- **Always** an image: per-anime TMDB backdrop when the card is about a specific anime
  (via existing `anime_art_key`/`ensure_anime_art`/`next_anime_art`), else the recurring
  Lelouch character art (`pick_artwork("lelouch")`) as fallback. No card ever ships
  imageless; no card ever ships image-only.
- Copy written **as Lelouch** — measured, imperious, chess/strategy metaphors, first
  person. E.g. paused-requests → *"The board is frozen for now. I don't move pieces I
  can't win with — return shortly and we'll resume the game."* Kept to a real paragraph,
  not one terse line. All strings live in `lelouch_voice.py` so tone stays consistent and
  is revisable in one place.

Acceptance: navigating forward then Back always lands on a full card (image + info +
keyboard), never a bare image or a stripped message.

---

## 2. Kill the routing graveyard

Rewrite `bots/lelouch/app.py` into one authoritative dispatcher:

- Single `^lelouch\|` router = the menu backbone: `home`, `admin`, `settings`, `set|<key>`,
  `reqtoggle`, and the management actions (below). `/admin`, `/settings`, `/start`, `/help`,
  `/myrequests` command handlers **delegate** to the same builders (no second copy).
- Add the missing bridges so welcome-screen buttons resolve:
  - bare `home` and `admin|home` → Lelouch home / admin panel.
  - `queue|view|<page>` → a Lelouch queue screen (requests + work, paginated).
  - `batch|new` already reused; keep, but route its confirm flow through §5.
- Every unknown action answers with a themed toast instead of silently dying.

Acceptance: every button on every Lelouch screen either navigates or shows an explicit
toast — zero dead taps. I'll enumerate the callbacks and assert coverage in a test.

---

## 3. Force-join gate (requesting only)

- Reuse `nekofetch/bots/force_sub.py::channels_to_join` (already fail-open on misconfig).
- New `shared/request_gate.py` helper `ensure_can_request(client, container, user)` → when
  channels are missing, send a **Lelouch-voiced join card** (recurring artwork, "join to
  play" copy) with join buttons + a "✓ I've joined" recheck button; return False.
- Called at the top of the request flow (`req|new` and the text-search entry), **not** on
  `/start` or browsing. Admins/staff bypass.

Acceptance: non-member tapping "Request Anime" gets the join card; after joining +
recheck, flows straight into title entry. Browsing/help/myrequests still open freely.

---

## 4. Requests vs Work — the data split

- **Migration** `20260718_xxxx_add_work_items.py`: new `work_items` table
  (`id, code, added_by_admin_id, anime_title, anime_doc_id, franchise_data JSONB, stage,
  status, assigned_admin_id, created_at, updated_at`). Stage mirrors the pipeline
  (download→distribute→publish). **Work never counts against user request limits.**
- New `shared/work_service.py`: `add_batch(admin_id, titles) -> list[WorkItem]`,
  `list_open()`, `next_for_stage(stage)`, `claim/complete`. Registered on
  `Base.metadata` via `shared/models.py` so `create_all` + Alembic see it.
- **Requests** (user-facing) stay in the existing `requests` table + `RequestService`,
  unchanged except they now also feed the shared queue view.
- Both requests and work items flow into the **same download queue** for Levi, so §6's
  "pipeline never stalls" applies to both. A downed Senku/Gojo does **not** stop Levi
  pulling the next item — Levi keeps downloading + writing to storage; downstream picks up
  from the task list whenever it's back. (Levi already reads a task list, so this is a
  queue-drain guarantee + a test, not a rewrite.)

Acceptance: admin batches 3 titles → 3 work_items, 0 user-request-limit impact; user with
an active request still blocked from a 2nd (limit respected); queue view shows both.

---

## 5. Admin batch — left/right pagination confirm

Replace the reused NekoFetch batch confirm with a Lelouch paginated confirmer:

- `/batch` or `batch|new` → admin sends N titles (newline/comma separated).
- For each title we resolve a franchise (§7 provider chain) and build a **confirm card**
  (consistent grammar, that anime's backdrop). Present them **one at a time** with
  `◀ / ▶` pagination + `✓ This is it` / `✗ Skip` / `Done`. Left disabled on first,
  right disabled on last (pagination semantics you described).
- Confirmed titles become `work_items`; skipped are dropped. "Done" writes the batch and
  shows a summary card.

Acceptance: 4-title batch renders 4 swipeable confirm cards; first card's ◀ is inert;
confirming 3 + skipping 1 creates exactly 3 work_items.

---

## 6. Provider chain — consistent card regardless of source

One `resolve_franchise(container, query)` used by both single-request and batch:

1. AniList (via `container.anilist`, already `ResilientMetadataClient`).
2. On miss → **Jikan/MAL** (already the built-in fallback inside `ResilientMetadataClient`
   — confirm it's engaged; no new client needed).
3. On miss → **Acute bot via userbot** (`providers/acute_bot.py::fetch_from_acutebot`),
   normalized into the same franchise dict.
4. Last resort → TMDB (kept, lowest priority for anime metadata).

All four normalize to the **same franchise dict shape**, so `confirm_franchise`/`card()`
render identically no matter the source. TMDB backdrops still fetched for artwork
regardless of metadata source.

Acceptance: forcing AniList to return None still yields a fully-populated confirm card
(from Jikan or Acute) with the same layout.

---

## 7. Management system (full, this round)

Real screens **and** real logic for the four bots' staff, driven from Lelouch:

- **Admin pool per bot**: assign/unassign admins to `lelouch|levi|senku|gojo`
  (`AdminAvailability.assigned_bots`), set weights (bias `AdminAssignmentEngine`).
- **Availability**: mark available / unavailable; the engine already skips unavailable.
- **Scheduled breaks**: add/clear `{start,end,reason}` windows; engine treats on-break as
  unavailable.
- **Working hours / modes**: per-admin active window; a mode switch (e.g. `normal` /
  `catch-up` / `paused`) stored in Redis, surfaced on the admin panel banner.
- **Reassignment**: move a task/work-item to another admin.
- **Idle reminders**: a scheduler job (reuse `container.scheduler`) that, when work is in
  line and an assigned admin has an open task they haven't progressed, DMs a Lelouch-voiced
  nudge — **suppressed while they're actively working** (i.e. only fires when the assigned
  item has had no state change within a threshold and the admin isn't mid-download). Same
  mechanism generalizes to all four stages.

Each is a proper card + keyboard under `lelouch|manage|…`, `lelouch|avail|…`,
`lelouch|hours|…`, etc. No more "coming next round" placeholder screens.

Acceptance: assign an admin to Levi + set weight → engine routes the next item to them;
add a break covering now → they're skipped; idle reminder fires for a stale open task and
does **not** fire for one that changed state within the window (unit-tested with a fake
clock).

---

## 8. Rebuild the cards that suck

- **Request receipt**: full grammar (already partly there) + guaranteed per-anime backdrop.
- **Dedup "already requested"**: one card, that anime's art, Lelouch voice, jump button.
- **Admin new-request/new-work DM**: rich card, backdrop, Open-in-Levi button.
- **Paused / limit-reached / not-found / join-required**: all re-voiced as Lelouch,
  all carry artwork.

---

## 9. Tests + verification

- `tests/test_lelouch_routing.py`: assert every callback a Lelouch screen emits has a
  matching handler (introspect registered regexes) — guards against regressions of §2.
- `tests/test_work_items.py`: batch→work_items, limit isolation, queue-drain when
  downstream bots are "down".
- `tests/test_management.py`: assignment weighting, breaks, idle-reminder fire/suppress
  (fake clock).
- Extend `tests/test_artwork.py` coverage for the new card paths.
- Run full suite (`pytest`) — must stay green. Syntax-check all touched files.
- Migration: `alembic upgrade head` dry-run against the dev DB.

---

## 10. Rollout order (so nothing's half-wired)

1. Card grammar + Lelouch voice catalog (§1).
2. Routing rewrite + kill dead taps (§2) — fixes the visible breakage first.
3. Force-join gate (§3).
4. Work-items table + service + migration (§4).
5. Provider chain unify (§6).
6. Batch pagination confirm (§5).
7. Management system (§7).
8. Card polish pass (§8).
9. Tests + full verification (§9).
10. Commit + push (per standing instruction).

---

### Open question I'm assuming a default on
- **Idle-reminder threshold**: defaulting to a configurable value (env/settings, e.g.
  45 min of no state change) rather than hard-coding. Say the word if you want a specific
  number.
