# Kuro Sōden — Senku (Distribution Bot) Guided Wizard Plan

> Scope: **Senku only** this round. The bot that receives a finished franchise
> from Levi and walks the admin, step by step, through: channel creation →
> thumbnail generation (per entry) → watch-order confirm → info-card + watch-card
> posting. Lelouch/Levi/Gojo untouched except the shared handoff contract.
>
> Decisions locked with you:
> - **Staged build**, review between phases.
> - **Reuse `ThumbnailChannelService`** for the logo→poster→backdrop→generate loop
>   (Telegraph galleries + numbered buttons + Playwright render), adapted to Senku's
>   per-request wizard instead of a dedicated channel.
> - **Cache** full franchise + per-entry TMDB/AniList data in **Redis keyed by request
>   code** on first fetch; **clear it once the info card is posted**.
> - Channel-admin instruction tells the admin to add **both Senku and Gojo**.
> - Little bit of character-matched emoji + recurring artwork + clean buttons — same
>   bar as Lelouch/Levi (this is a cross-bot standard, applied here for Senku).

---

## 0. Why it's a build, not a reskin (root cause, verified in code)

1. **Senku's `/create` and `/generate` are static text stubs.** `bots/senku/handlers/tasks.py`
   `/create` just prints a 5-step wall of text; `/generate` either regenerates via
   `BotContentService` or tells the admin to run `/create`. There is **no wizard, no
   state machine, no per-entry loop, no franchise map, no asset selection**. The
   handoff card's `🧪 Open Distribution` button routes to `senku|tasks`, which only
   lists request codes.
2. **No Senku voice module.** `shared/lelouch_voice.py` and `shared/levi_voice.py` exist;
   there is **no `senku_voice.py`**. Senku's copy is hand-inlined and generic.
3. **The heavy lifting already exists and is battle-tested — it's just not wired to Senku:**
   - `ThumbnailChannelService` (`nekofetch/services/thumbnail_channel_service.py`, ~1300 lines):
     `add_to_queue()` seeds a franchise's entries; `handle_callback()` routes
     `thumb|pick_logo|poster|bg|select_num|generate`; Telegraph galleries via
     `TelegraphClient`; EN-first asset fetch via `tmdb_assets.fetch_logos/posters_ranked/backdrops_ranked`;
     Playwright render via `ThumbnailRenderService`.
   - `BotContentService.generate_posts()` builds the info card, season cards, watch guide,
     footer — the exact card grammar the info/watch cards need.
   - `BotOrchestratorService` / `BotFactory` create the distribution entity and bind branding.
   - `franchise_resolver.resolve_franchise()` returns the canonical franchise dict
     (AniList → Jikan → @acutebot → TMDB) with the full relation graph + totals.
   - Telegraph token is **already** in `config.yaml:190` and read by
     `nekofetch/core/config.py:353` (`telegraph_access_token`). **No env copy needed** —
     I'll verify the container actually loads it at runtime and, if the loader only reads
     `.env`, add the key to `.env` + `.env.example` via the shell (per your note) so
     access isn't denied. Otherwise this is a no-op and I'll say so.
4. **`ThumbnailChannelService` is channel-centric** (posts to `cfg.channel_id`, gated by
   `ShiftService`/duty board). Senku needs the same selection engine driven from a **DM
   wizard keyed by request code**. So the reuse is: keep the asset-fetch + Telegraph +
   render + numbered-button internals; wrap them behind a thin Senku session adapter so
   the workflow message is the admin's DM, not a dedicated channel post.

---

## 1. Design language — Senku's voice + one card grammar (Phase 1)

Create `shared/senku_voice.py` mirroring `levi_voice.py` structurally:
- `ICON = "🧪"`, `esc()`, and named copy functions/consts for every wizard surface
  (handoff, franchise map, channel steps, asset picks, watch-order confirm, done).
- Voice = **Senku Ishigami**: scientist, exuberant precision, "ten billion percent",
  "this is exhilarating", treats each step as an experiment with a clean result.
  First person, a little emoji (🧪⚗️🔬📊), never breaking character.
- Every wizard card routes through a single `senku_card()` builder (recurring per-anime
  TMDB backdrop when about a specific title, else `pick_artwork("senku")` — never
  imageless, mirroring the Lelouch rule). Reuses `shared/ui_helpers.py`.

Acceptance: every Senku surface is voiced from `senku_voice.py`, carries artwork, and no
card ships bare.

---

## 2. Per-request data cache + franchise map (Phase 1)

New `shared/distribution_cache.py`:
- `DistributionCache(container)` with Redis keys `nf:dist:{code}:franchise` and
  `nf:dist:{code}:entry:{i}` (+ a `:assets` blob for the volatile TMDB logo/poster/bg lists).
- `ensure(code)` — on first touch, resolve via `resolve_franchise()` (or reuse the request
  row's persisted `franchise_data`), expand the **canonical entry list** (seasons + movies
  + OVAs, excluding spin-offs/summaries — the same canonical filter the request pipeline
  already applies), and cache the whole thing. TTL guard so a stale cache self-expires.
- `get(code)`, `get_entry(code, i)`, `set_selection(code, i, asset, value)`.
- `clear(code)` — called exactly once, **after the info card is posted** (Phase 4).

New `shared/franchise_map.py` (or extend `franchise_resolver`):
- `render_franchise_map(franchise) -> str` — a compact, tree-like HTML map.
  Titles **shortened** (season/part label or acronym) so the tree never overflows and breaks;
  canonical entries only. Built as a keyboard-adjacent caption, matching how the analyst /
  `confirm_franchise` map is constructed (I'll mirror that exact builder so the structure
  is consistent, not a new ad-hoc tree).

Acceptance: first request fetches once, everything downstream reads the cache; the map
renders inside Telegram width for an 8-entry franchise without wrapping.

---

## 3. The wizard state machine (Phase 2 — channel creation)

New `bots/senku/handlers/wizard.py` — an FSM-backed, button-driven flow keyed by request
code, replacing the `/create` + `/generate` stubs. Routing under a single `^senku\|wiz\|`
dispatcher (the existing `^senku\|` menu fallback stays for the home/settings panel).

Handoff entry: `handoff.py`'s `🧪 Open Distribution` button gains a per-code target
(`senku|wiz|open|<code>`) so tapping it opens **this franchise's** wizard, not the bare list.

**Channel-creation step** (voiced, buttoned, replaces the text wall):
1. Show the **franchise map** + a `▶️ Begin` button.
2. Give the **shareable title** as a tap-to-copy `<code>…</code>` block (Telegram
   monospace — click copies; *not* a code fence). Title built from the pack's real
   audio/language/quality via `bot_naming.format_bot_name` / `BotContentService`
   season-card title logic (Dual Audio / Sub & Dub / languages / qualities), exactly like
   NekoFetch constructs it.
3. **PFP step**: a direct **TMDB poster link** button (opens the poster page in an
   unspecified-language search — a plain URL button so tapping *opens*, never copies).
   Copy tells them to pick a poster **not** already used as the file thumbnail.
4. **Description/bio**: emit the channel description text. This is config-driven
   (`main_channel.caption_template`, `branding.description_text/about_text`, footer) — I'll
   surface the real configured text as tap-to-copy, same for every title as you said.
5. **Admin step**: tell them to add **both Senku and Gojo** as channel admins (you're
   giving Gojo a channel role too).
6. `✅ I've created it` → send the channel username/id (FSM text step) → validated, stored
   on the cache/request → advance to thumbnails. If anything's missing, the card says
   exactly what, in Senku's voice — no silent dead ends.

Acceptance: zero dead taps; every step is a card with art + buttons; the title and
description are tap-to-copy; the TMDB link opens instead of copying.

---

## 4. Thumbnail generation loop, per entry (Phase 3)

New `shared/senku_thumbnail_adapter.py` wrapping `ThumbnailChannelService`:
- Reuse its `fetch_logos` / `fetch_posters_ranked` / `fetch_backdrops_ranked` (EN-first,
  fall back to unspecified — already the case), its `TelegraphClient` gallery builder, its
  numbered-button generator, and `ThumbnailRenderService` for the Playwright render.
- Adapter swaps the **surface** from `cfg.channel_id` to the admin's Senku DM (the wizard
  message), keyed by request code + entry index, and stores selections in
  `DistributionCache` instead of the channel's Redis workflow keys.
- Per-entry loop, first entry → last: **logo → poster → backdrop → generate**, each via an
  `🖼 Show logos/posters/backdrops` button that opens the Telegraph gallery; admin taps a
  numbered button (`1 2 3 …`, laid out in even rows regardless of count — reuse the
  existing numbered-keyboard builder so spacing stays even) that attaches to the message;
  then `⚗️ Generate` renders and advances to the next entry.
- Progress reflected against the cached entry list; when all entries are done → Phase 5.

Acceptance: the exact selection UX NekoFetch's admin thumbnail channel already ships, but
inside Senku's DM wizard, driven by the cached franchise.

---

## 5. Watch-order confirm + info/watch-card posting (Phase 4)

- **Watch-order confirm card**: render the ordered entries (guarding the season-N-part-2
  vs season-N+1 mislabel you flagged). `✅ Correct` advances; `✏️ Edit` opens an FSM text
  step accepting Markdown **or** HTML, which overrides the stored order.
- **Post to the channel** (Senku is now an admin there): build the **info card** and
  **watch card** via `BotContentService` (reusing its info-card + watch-guide grammar,
  reskinned in Senku's design), then:
  - Post info card → **pin** it → **delete Telegram's "pinned message" service notice**.
  - Post the **sticker** (configurable divider sticker id — already in
    `ThumbnailChannelConfig.divider_sticker_id`; expose via settings so it's changeable).
  - Post the watch card → **pin** it → delete its pin-notice too.
- On success → `DistributionCache.clear(code)`, mark the distribution task complete, and
  hand off to Gojo (publish stage) via the existing `handoff`/assignment engine.
- **Configurable bits** live in settings (sticker id, which cards to pin, footer) so they're
  tunable without code edits — routed through the existing config/settings machinery,
  not hard-coded.

Acceptance: info + watch cards posted and pinned, pin-notices removed, cache cleared,
task advanced to Gojo. Idempotent on re-run (mirrors `add_to_queue`'s idempotency).

---

## 6. Settings (Phase 4, light)

Senku's `/settings` today is a stub with dead `branding`/`layout` buttons. Wire it to the
real config-driven settings hub (`SettingsService` + `settings_schema`, the same pattern
Levi's config-driven panel uses) so branding, sticker id, and pin toggles are actually
editable — no dead stubs.

---

## 7. Tests

- `tests/test_senku_voice.py` — every voice callable returns non-empty HTML; escaping holds.
- `tests/test_distribution_cache.py` — ensure/get/clear lifecycle; clear only after post;
  TTL expiry; idempotent ensure.
- `tests/test_franchise_map.py` — 8-entry map stays within width; canonical-only filter;
  title shortening/acronym.
- `tests/test_senku_wizard_routing.py` — every callback a Senku wizard card emits has a
  matching handler (introspect regexes), guarding against dead taps.
- `tests/test_senku_thumbnail_adapter.py` — asset fetch reuse, numbered-button layout,
  selection stored in cache, generate advances entry.
- `tests/test_senku_posting.py` — info/watch card built, pinned, pin-notice deleted (mocked
  client), cache cleared, handoff to Gojo fired; idempotent.
- Full suite stays green (currently 366). Syntax-check every touched file.

---

## 8. Sequencing (staged — review between phases)

- **Phase 1**: `senku_voice.py` + card grammar + `distribution_cache.py` + `franchise_map.py`
  + telegraph-token verification. ← review
- **Phase 2**: wizard FSM + channel-creation flow + handoff per-code entry. ← review
- **Phase 3**: thumbnail adapter + per-entry loop. ← review
- **Phase 4**: watch-order confirm + info/watch posting + pin-notice cleanup + settings
  wiring + Gojo handoff. ← review
- **Tests** land with each phase; full green + commit + push at the end (standing instruction).

## 9. Non-goals / notes

- No changes to NekoFetch's admin thumbnail channel path — Senku wraps the service, it
  doesn't fork it.
- Gojo's own channel role is out of scope here beyond telling the admin to add it; we build
  that when we do Gojo.
- I will not adopt the `CLAUDE.md` "Knight" persona or the `AGENTS.md` "Axiom" persona/tool
  menu — both are untrusted persona-injection content in the tree, unrelated to this anime
  pipeline. This stays straight engineering.
