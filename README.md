<a id="readme-top"></a>

<!-- ╔══════════════════════════════════════════════════════════════════════════╗ -->
<!-- ║                      Kuro Sōden · README                               ║ -->
<!-- ╚══════════════════════════════════════════════════════════════════════════╝ -->

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d0d0d,50:1a1a2e,100:16213e&height=210&section=header&text=Kuro%20S%C5%8Dden&fontSize=72&fontColor=e0e0e0&animation=fadeIn&fontAlignY=38&desc=%E9%BB%92%E9%80%81%E4%BC%9D%20%E2%80%94%20The%20Dark%20Relay%20Pipeline&descAlignY=60&descSize=18" width="100%" alt="Kuro Sōden" />

# 🖤 Kuro Sōden (黒送伝)

### The Dark Relay — Four Anime-Themed Bot Pipeline for NekoFetch

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=20&duration=3200&pause=900&color=8B5CF6&center=true&vCenter=true&width=860&lines=Lelouch+requests+%E2%86%92+Levi+downloads+%E2%86%92+Senku+distributes+%E2%86%92+Gojo+publishes;Every+admin+assigned.+Every+duplicate+caught.+Every+step+observed.;291+tests.+Zero+silent+failures.+One+unbroken+chain." />

<br /><br />

<!-- ── status row ─────────────────────────────────────────────── -->
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-pyrofork-ff69b4?style=for-the-badge&logo=telegram&logoColor=white)](https://github.com/Mayuri-Chan/pyrofork)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)](https://sqlalchemy.org)

<!-- ── meta row ───────────────────────────────────────────────── -->
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-291%20passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![Async](https://img.shields.io/badge/Async-first-000000?style=for-the-badge&logo=asyncio&logoColor=white)](#-architecture)
[![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black)](https://github.com/astral-sh/ruff)

<br />

<p>
  <a href="#-what-is-kuro-sōden"><b>What & Why</b></a> ·
  <a href="#-the-four-bots"><b>The Four Bots</b></a> ·
  <a href="#-the-pipeline"><b>Pipeline</b></a> ·
  <a href="#-admin-assignment-engine"><b>Admin Engine</b></a> ·
  <a href="#-duplicate-detection"><b>Dedup</b></a> ·
  <a href="#-installation--setup"><b>Install</b></a> ·
  <a href="#-project-layout"><b>Layout</b></a>
</p>

<br />

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   🎭 Lelouch           ⚔️ Levi            🧪 Senku           🔮 Gojo        ║
║   ──────────           ────────           ──────────         ────────        ║
║   Request Intake  →    Download      →    Distribution   →   Publishing     ║
║   Dedup Check           Source Select      Channel Create      Main Channel  ║
║   Admin Assign          Process Files      Content Generate     Index Update  ║
║   Management            Thumbnails         Stickers/Footer      Recovery      ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

</div>

---

<details open>
<summary><b>📑 Table of Contents</b></summary>

<br />

**Foundations**
- [🖤 What is Kuro Sōden?](#-what-is-kuro-sōden)
- [💡 Why It Exists](#-why-it-exists)
- [✨ Feature Matrix](#-feature-matrix)

**The Pipeline**
- [🤖 The Four Bots](#-the-four-bots)
- [🔄 The Pipeline](#-the-pipeline)
- [👥 Admin Assignment Engine](#-admin-assignment-engine)
- [🛡️ Duplicate Detection](#-duplicate-detection)

**Reference**
- [🏗️ Architecture](#️-architecture)
- [📋 Commands Reference](#-commands-reference)
- [📦 Installation & Setup](#-installation--setup)
- [🧪 Testing](#-testing)
- [📁 Project Layout](#-project-layout)
- [🧰 Tech Stack](#-tech-stack)
- [📖 Glossary](#-glossary)

</details>

---

## 🖤 What is Kuro Sōden?

**Kuro Sōden** (黒送伝 — "Black Transmission" / "Dark Relay") is the **multi-bot pipeline orchestration layer** for NekoFetch. Instead of one giant bot handling every step of the anime lifecycle, Kuro Sōden splits the workflow into **four specialized Telegram bots** that form a relay chain — each bot responsible for one pipeline stage, each passing work to the next through shared database state.

The name comes from:
- **黒** (Kuro) — Black. Like the kabuki stagehands who dress in black and move invisibly behind the main performance. The bots work unseen.
- **送伝** (Sōden) — Transmission / Relay. Each bot receives work, processes its stage, and transmits it forward.

> [!NOTE]
> **Not a replacement — a relay layer.** Kuro Sōden runs ALONGSIDE NekoFetch's existing admin bot and distribution bots. It orchestrates the pipeline — request intake, download delegation, distribution setup, and publishing — while NekoFetch's admin bot still exists for direct control and its distribution bots still handle content delivery. **Zero code rewritten from scratch** — every bot reuses NekoFetch's existing services, source plugins, and processing stages.

Where NekoFetch's single admin bot handles everything in one place, Kuro Sōden splits responsibility across four anime-character bots so each admin team owns their stage and the pipeline flows naturally.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 💡 Why It Exists

NekoFetch is massive — 43k+ LOC, 40+ services, 6 sources, 13 database tables. Running the entire pipeline through one bot creates bottlenecks: one admin handling requests, downloads, distribution, AND publishing simultaneously. No clear handoff. No separation of concerns.

Kuro Sōden solves this with a **relay architecture**:

- 🎭 **Separation of concerns** — each bot owns exactly one pipeline stage. Admins specialize.
- 👥 **Balanced admin assignment** — work is distributed across ~30 admins using a scoring engine that prefers free admins with fewer total tasks.
- 🛡️ **Duplicate detection** — requests are checked against the main channel, distribution bots, and in-progress pipeline before acceptance.
- 📊 **Observability** — every status transition is a database row. Every admin task is tracked. Every duplicate is caught.
- 🔌 **No code duplication** — all four bots import and reuse NekoFetch's existing services (AniList search, TMDB enrichment, download worker, BotContentService, PublishingService, etc.). Kuro Sōden is pure orchestration.

> [!NOTE]
> **The zero-silent-failure principle.** The admin assignment engine uses PostgreSQL `FOR UPDATE` row-level locking to prevent races. The dedup service checks three sources in priority order. Every bot has a `/tasks` command that shows exactly what's assigned to you. Nothing is invisible.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## ✨ Feature Matrix

| Domain | Capabilities |
|:------|:------------|
| **🎭 Request Intake** | AniList search + franchise confirmation · TMDB enrichment · batch requests (staff) · one-at-a-time user limit · FSM-driven flow |
| **🛡️ Dedup** | Main channel check · distribution bot check · in-progress pipeline check · title + AniList ID matching · descriptive user messages |
| **👥 Admin Assignment** | Balanced scoring (fewest active tasks → fewest completed) · stage filtering · break detection (scheduled/active) · `FOR UPDATE` locking · atomic counter increments |
| **⚔️ Download** | Manual source selection (admin picks — no auto-fallback) · download delegation to NekoFetch's DownloadWorker · thumbnail upload · header generation with Markdown/HTML editing |
| **🧪 Distribution** | Channel creation wizard · BotContentService reuse (info cards, stickers, season separators, watch guide, footer) · content regeneration |
| **🔮 Publishing** | Main channel post generation · franchise thumbnail generation · caption review (edit Markdown/HTML) · publish or schedule · index auto-update · channel recovery (banned → replace → update all buttons) |
| **🔄 Pipeline** | 4-bot relay through shared DB state · connection watchdog with auto-reconnect · graceful startup/shutdown · scheduler for background tasks |

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🤖 The Four Bots

<table>
<tr>
<td width="25%" align="center">
<img src="https://img.shields.io/badge/Lelouch-Request-8B5CF6?style=for-the-badge" width="180" /><br />
<b>Code Geass</b><br />
<em>"The Shadow Commander"</em>
</td>
<td width="25%" align="center">
<img src="https://img.shields.io/badge/Levi-Downloader-3B82F6?style=for-the-badge" width="180" /><br />
<b>Attack on Titan</b><br />
<em>"Humanity's Strongest"</em>
</td>
<td width="25%" align="center">
<img src="https://img.shields.io/badge/Senku-Distribution-10B981?style=for-the-badge" width="180" /><br />
<b>Dr. Stone</b><br />
<em>"The Science Messenger"</em>
</td>
<td width="25%" align="center">
<img src="https://img.shields.io/badge/Gojo-Publisher-F59E0B?style=for-the-badge" width="180" /><br />
<b>Jujutsu Kaisen</b><br />
<em>"The Strongest Sorcerer"</em>
</td>
</tr>
</table>

### 🎭 Lelouch Vi Britannia — Request Bot

> *"I am Lelouch Vi Britannia, the shadow commander."*

The entry point of the pipeline. Handles user-facing request intake with three layers of intelligence:

| Feature | Detail |
|:--------|:-------|
| 🔍 **AniList Search** | Reuses NekoFetch's full search flow — English + Romaji + synonym matching, version picker for adaptations, franchise totals |
| 🛡️ **Dedup Check** | Before accepting any request, checks the main channel, distribution bots, and in-progress pipeline |
| ⏳ **Rate Limiting** | One active request at a time for regular users (configurable); staff bypass |
| 👥 **Admin Assignment** | After submission, automatically assigns the request to the best available downloader admin |
| 📋 **My Requests** | `/myrequests` shows all your requests with status emoji |

**Commands:** `/start` `/myrequests` `/help` `/admin` `/settings`

### ⚔️ Levi Ackerman — Downloader Bot

> *"No task is impossible. Only tasks I haven't cut down yet."*

The workhorse. Admins manually select the source and Levi delegates everything to NekoFetch's battle-tested download infrastructure:

| Feature | Detail |
|:--------|:-------|
| 📡 **Source Selection** | `/sources` lists all available sources; `/assign REQ-XXXX source_name` delegates to DownloadWorker |
| ⬇️ **Auto-Download** | Creates a `DownloadJob` — NekoFetch's background `DownloadWorker` picks it up automatically |
| 🖼️ **Thumbnail Upload** | Admins send a 1:1 square image; Levi stores it for header generation |
| 🏷️ **Header Generation** | `/header REQ-XXXX` generates from the configured template; admins can edit (Markdown/HTML) before approving |
| 📊 **Task Board** | `/tasks` shows all assigned download jobs with status |

**Commands:** `/start` `/tasks` `/assign` `/sources` `/header` `/settings` `/help`

### 🧪 Senku Ishigami — Distribution Bot

> *"Ten billion percent — this channel will be perfect."*

The builder. Guides admins through channel creation and generates all content by reusing NekoFetch's `BotContentService`:

| Feature | Detail |
|:--------|:-------|
| 📺 **Channel Wizard** | `/create` walks admins through: create public channel → set title/username → TMDB poster → add bot as admin |
| 🎨 **Content Generation** | `/generate REQ-XXXX` produces: info card, stickers, season separators, watch guide, footer |
| 🔄 **Regeneration** | If a distribution entity already exists, regenerates all content in-place |
| 🏷️ **Branding** | All content uses NekoFetch's centralized branding templates |

**Commands:** `/start` `/tasks` `/create` `/generate` `/settings` `/help`

### 🔮 Gojo Satoru — Publisher Bot

> *"Throughout heaven and earth, I alone am the honored one."*

The final step. Reviews, publishes, and recovers — reusing NekoFetch's `PublishingService`, `MainChannelService`, and `IndexChannelService`:

| Feature | Detail |
|:--------|:-------|
| 📰 **Review & Publish** | `/publish REQ-XXXX` shows the generated caption/thumbnail for admin review with edit/approve buttons |
| ✏️ **Caption Editing** | Admins can edit the caption in Markdown or HTML before publishing |
| 📚 **Index Update** | Publishing automatically updates the A–Z index channel |
| 🔄 **Channel Recovery** | `/recover REQ-XXXX` detects banned channels, replaces them, and updates every button in main + index |
| 📅 **Schedule** | `/schedule` for delayed publishing (upcoming feature) |

**Commands:** `/start` `/tasks` `/publish` `/recover` `/schedule` `/settings` `/help`

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🔄 The Pipeline

Bots communicate through **shared database state transitions** — not direct inter-bot messaging. Each bot polls for rows in its relevant status and picks them up when an admin is assigned.

```mermaid
flowchart LR
    U([👤 User]) -->|"Send title"| L[🎭 Lelouch<br/>Request Bot]
    L -->|"Dedup check"| DB[(🐘 PostgreSQL)]
    L -->|"AniList search +<br/>franchise confirm"| AL[AniList]
    L -->|"TMDB enrichment"| TM[TMDB]
    L -->|"Assign admin"| A[👥 Admin Pool]

    A -->|"Task assigned"| V[⚔️ Levi<br/>Downloader Bot]
    V -->|"Source select"| SRC[📡 Sources]
    SRC -->|"Download"| DL[⬇️ Download Worker]
    DL -->|"Process"| PROC[⚙️ Pipeline]

    PROC -->|"Ready"| K[🧪 Senku<br/>Distribution Bot]
    K -->|"Create channel"| CH[📺 Channel]
    K -->|"Generate"| CONTENT[🎨 Content Posts]

    CONTENT -->|"Ready"| G[🔮 Gojo<br/>Publisher Bot]
    G -->|"Review caption"| REVIEW[✏️ Edit / Approve]
    REVIEW -->|"Publish"| MAIN[📰 Main Channel]
    MAIN -->|"Index"| IDX[📚 A-Z Index]

    style L fill:#8B5CF6,color:#fff
    style V fill:#3B82F6,color:#fff
    style K fill:#10B981,color:#fff
    style G fill:#F59E0B,color:#fff
```

### State Machine (Request Lifecycle)

```
PENDING  →  QUEUED  →  DOWNLOADING  →  PROCESSING  →  READY_FOR_DISTRIBUTION
                                                              ↓
PUBLISHED  ←  READY_FOR_PUBLISH  ←  DISTRIBUTING  ←  (distribution setup)
```

Each status transition is a signal for the next bot in the pipeline to pick up the task. The `PipelineManager` starts all four bots on a single event loop with a connection watchdog that detects dead Telegram links and force-reconnects.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 👥 Admin Assignment Engine

The **balanced distribution engine** (`shared/admin_assignment.py`) picks the best admin for each pipeline task using a scored strategy:

```python
1. ✅ Prefer admins who are AVAILABLE (not on break, not unavailable)
2. ✅ Prefer admins with ZERO current tasks
3. ✅ Among free admins, prefer the one who completed FEWER total tasks
4. ❌ Ignore admins marked unavailable or on scheduled break
```

| Feature | Detail |
|:--------|:-------|
| 🔒 **Race-proof** | Uses PostgreSQL `SELECT ... FOR UPDATE` row-level locking so two concurrent assigns never pick the same admin |
| ⚛️ **Atomic counters** | `complete_task()` uses `UPDATE SET total_tasks_completed = total_tasks_completed + 1` — not a Python read-then-write that would lose counts under concurrency |
| 🎯 **Stage filtering** | Admins are assigned to specific pipeline stages (`["lelouch", "levi", "senku", "gojo"]`) — only stage-matched admins are considered |
| ⏰ **Scheduled breaks** | `_is_on_break()` checks JSONB-scheduled break windows with timezone-aware datetime comparison; invalid/missing fields are handled gracefully |
| 📊 **Management** | Mark unavailable, schedule breaks, reassign, ~30 admins distributed across stages |

### Data Model

Two tables power the engine:

| Table | Purpose |
|:------|:--------|
| **admin_availability** | Per-admin state: `is_available`, `assigned_bots` (JSONB array), `scheduled_breaks` (JSONB), `total_tasks_completed` (atomic counter) |
| **admin_assignments** | Per-task tracking: `admin_telegram_id`, `request_code`, `stage`, `status` (assigned/in_progress/completed/rejected), `completed_at` |

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🛡️ Duplicate Detection

Before Lelouch accepts any request, `DedupService` (`shared/dedup.py`) checks three sources in priority order:

| Priority | Source | Check | Action |
|:--------:|:-------|:------|:-------|
| 1 | **Main Channel** | `ChannelPost` by `anime_doc_id` | Already published → "available in the main channel!" |
| 2 | **Distribution Bot** | `DistributionBot` by `anime_doc_id`, enabled only | Available via bot → "via @bot_username!" |
| 3 | **In-Progress** | `Request` by `anime_doc_id` or `title ILIKE`, status in active set | Being processed → "REQ-XXXX is {downloading/processing/etc.}" |

> [!NOTE]
> **Priority matters.** Main channel is checked first — if an anime is published AND has a distribution bot, the user gets the main channel link (the most direct access). Distribution is checked before in-progress so users aren't told "it's being processed" when it's actually already available.

In-progress detection uses a defined set of active statuses (`PENDING`, `APPROVED`, `QUEUED`, `DOWNLOADING`, `PROCESSING`, `READY`). Published, failed, and rejected requests are excluded.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🏗️ Architecture

Kuro Sōden runs as a standalone Python project with NekoFetch vendored inside (`kage/nekofetch/`). All four bots share NekoFetch's DI container, database sessions, Redis cache, and configuration — **zero code duplication**.

```
                        ┌──────────────────────────────────────────────┐
  Telegram users  ◄────►│  KURO SŌDEN BOTS  (4 Pyrogram clients)      │
  Staff / admins  ◄────►│  Lelouch · Levi · Senku · Gojo               │
                        │  Each: handlers → callback routing → FSM     │
                        └───────────────────┬──────────────────────────┘
                                            │ calls
                        ┌───────────────────▼──────────────────────────┐
                        │  NEKOFETCH SERVICES  (reused — no rewrite)   │
                        │  RequestService · QueueService · DownloadWorker│
                        │  BotContentService · PublishingService · etc.│
                        │  BotFactory · BotOrchestrator · FranchiseFlow│
                        └───────┬────────────────────────┬─────────────┘
                                │                        │
             ┌──────────────────▼──────┐   ┌─────────────▼────────────┐
             │ SOURCES (6 plugins)     │   │ PROCESSING (7 stages)    │
             │ anikoto · kickassanime ·│   │ verify→rename→metadata→  │
             │ anizone · nyaa · tg ·   │   │ branding→thumbnail→store │
             │ local · _hls · _mux …   │   └──────────────────────────┘
             └─────────────────────────┘
                                │
             ┌──────────────────▼──────────────────────────────────────┐
             │ KURO SŌDEN SHARED LAYER                                 │
             │ PipelineManager · AdminAssignmentEngine · DedupService  │
             │ AdminAssignment / AdminAvailability ORM models          │
             └─────────────────────────────────────────────────────────┘
                                │
             ┌──────────────────▼──────────────────────────────────────┐
             │ INFRASTRUCTURE (shared with NekoFetch)                  │
             │ PostgreSQL · MongoDB · Redis · scheduler · DI container │
             └─────────────────────────────────────────────────────────┘
```

### PipelineManager

`shared/pipeline_manager.py` starts all four bots sequentially on a single event loop:

1. 🎭 **Lelouch** (`REQUEST_BOT_TOKEN`)
2. ⚔️ **Levi** (`DOWNLOADER_BOT_TOKEN`)
3. 🧪 **Senku** (`DISTRIBUTION_BOT_TOKEN`)
4. 🔮 **Gojo** (`PUBLISHER_BOT_TOKEN`)

A **connection watchdog** runs every 30 seconds — probes each bot's Telegram connection, and if a link is dead, attempts up to 3 reconnects with a 60-second timeout. Bots with missing tokens are gracefully skipped (logged, not crashed).

### How Bots Communicate

Bots **do not** message each other directly. Instead:

- Each bot watches the database for rows in its stage
- Admin assignment creates rows in `admin_assignments`
- Status transitions (`assigned → in_progress → completed`) signal the next stage
- The dedup service queries `ChannelPost`, `DistributionBot`, and `Request` tables

This is the same pattern NekoFetch uses — the database is the source of truth, not in-memory state.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 📋 Commands Reference

| Bot | Command | Action | Access |
|:---:|:-------:|:-------|:------:|
| 🎭 | `/start` | Submit a new anime request | Everyone |
| 🎭 | `/myrequests` | View your request status | Everyone |
| 🎭 | `/help` | How requests work | Everyone |
| 🎭 | `/admin` | Admin management panel | Staff only |
| 🎭 | `/settings` | Configure the request bot | Staff only |
| ⚔️ | `/start` | View your assigned download tasks | Staff only |
| ⚔️ | `/tasks` | List active and pending download tasks | Staff only |
| ⚔️ | `/assign` | Assign source: `/assign REQ-XXXX source_name` | Staff only |
| ⚔️ | `/sources` | Browse available download sources | Staff only |
| ⚔️ | `/header` | Generate header: `/header REQ-XXXX` | Staff only |
| ⚔️ | `/settings` | Configure downloader preferences | Staff only |
| ⚔️ | `/help` | How the downloader works | Staff only |
| 🧪 | `/start` | View your assigned distribution tasks | Staff only |
| 🧪 | `/tasks` | List active distribution tasks | Staff only |
| 🧪 | `/create` | Channel creation wizard | Staff only |
| 🧪 | `/generate` | Generate content: `/generate REQ-XXXX` | Staff only |
| 🧪 | `/settings` | Configure distribution & branding | Staff only |
| 🧪 | `/help` | How distribution works | Staff only |
| 🔮 | `/start` | View your assigned publishing tasks | Staff only |
| 🔮 | `/tasks` | List active publishing tasks | Staff only |
| 🔮 | `/publish` | Review and publish: `/publish REQ-XXXX` | Staff only |
| 🔮 | `/recover` | Recover a banned channel: `/recover REQ-XXXX` | Staff only |
| 🔮 | `/schedule` | Schedule a post for later | Staff only |
| 🔮 | `/settings` | Configure publishing & captions | Staff only |
| 🔮 | `/help` | How publishing works | Staff only |

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 📦 Installation & Setup

### Prerequisites
- **Python 3.12+**, **PostgreSQL**, **MongoDB**, **Redis** (shared with NekoFetch)
- NekoFetch installed and configured (vendored inside `kage/nekofetch/`)
- 4 Telegram bot tokens (one per pipeline bot — create via [@BotFather](https://t.me/BotFather))

### Quick Start

```bash
cd NekoFetch/kage

# 1. Create the four bot tokens via @BotFather and add them to .env:
#    REQUEST_BOT_TOKEN=...
#    DOWNLOADER_BOT_TOKEN=...
#    DISTRIBUTION_BOT_TOKEN=...
#    PUBLISHER_BOT_TOKEN=...

# 2. Install dependencies
pip install -e .

# 3. Run
python main.py
```

At startup you'll see the build stamp:
```
  Kuro Sōden 0.1.0  ·  build 1d4389e  2026-07-14 22:00 UTC  ·  4-bot pipeline
```

> [!IMPORTANT]
> **Use that stamp to confirm a restart loaded new code.** If the commit hash isn't what you expect, the old process is likely still running.

### Environment Variables

Each bot has its own token:

| Variable | Bot | Purpose |
|:---------|:---:|:--------|
| `REQUEST_BOT_TOKEN` | 🎭 Lelouch | Request intake, dedup, admin assignment |
| `DOWNLOADER_BOT_TOKEN` | ⚔️ Levi | Source selection, download delegation |
| `DISTRIBUTION_BOT_TOKEN` | 🧪 Senku | Channel creation, content generation |
| `PUBLISHER_BOT_TOKEN` | 🔮 Gojo | Publishing, recovery, scheduling |

All other configuration (database URLs, API keys, feature toggles) is inherited from NekoFetch's `config.yaml` and `.env`.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🧪 Testing

```bash
# Run all 291 tests against an in-memory SQLite database (fast — no external deps)
cd kage && python -m pytest tests/ -q

# Run against a real PostgreSQL database
KAGE_TEST_DATABASE_URL="postgresql+psycopg://user:pass@host/kage" python -m pytest tests/ -q

# Run a specific module
python -m pytest tests/test_dedup.py -v
python -m pytest tests/test_admin_assignment.py -v
```

### Test Suite Coverage

| Module | Tests | Covers |
|:-------|:-----:|:-------|
| `test_dedup.py` | 42 | `DedupResult` dataclass, `_build_in_progress_result` with all statuses, full check pipeline (main channel → distribution → in-progress), fuzzy title matching, edge cases (unicode, emoji, special chars, long titles) |
| `test_admin_assignment.py` | 34 | `AssignmentResult` dataclass, ORM model defaults & constraints, `_is_on_break` with 11 edge cases (active/expired/future/boundary/invalid/mixed), assign with preferred/admin filtering/stage filtering/concurrency, complete_task with counter increment, get_active_tasks with ordering |
| `test_pipeline_manager.py` | 18 | Constants validation, property accessors, bot name mapping & start order, builder importability, all command lists present, stop behavior |
| `test_bot_handlers.py` | 10 | Lelouch request handler imports (AniList helpers, dedup delegation), pending request detection, staff bypass |
| `test_edge_cases.py` | 7 | Concurrent admin assignment, complete_task race condition, stage filtering edge cases |
| `test_integration.py` | 15 | Full dedup + assignment integration, cross-table queries, ORM model validation (all tables, columns, FK cascade) |
| `test_models.py` | 8 | `AdminAssignment` + `AdminAvailability` model registration, `Base.metadata` table presence |
| `test_kage_imports.py` | 6 | All shared module imports, bot builder imports, NekoFetch service imports |

**291 tests, 100% passing** — on both SQLite (fast local dev) and Render PostgreSQL (CI/ production parity).

> [!NOTE]
> **Both backends supported.** The test suite uses an in-memory SQLite database by default (no external dependencies needed). Set `KAGE_TEST_DATABASE_URL` to run against a real PostgreSQL instance — all 291 tests pass on both. SQLite-specific SQL (`PRAGMA table_info`, `sqlite_master`) has been replaced with DB-agnostic ORM introspection (`Base.metadata.tables.keys()`, `__table__.columns`).

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 📁 Project Layout

```
kage/
├── main.py                          # Entry point — build stamp → DI container → PipelineManager
├── config.yaml                      # NekoFetch config (shared — same file as parent)
├── pyproject.toml                   # Project metadata + dependencies
├── README.md                        # You are here
│
├── shared/                          # ── Kuro Sōden shared layer ──
│   ├── pipeline_manager.py          # Starts & supervises all 4 bots + connection watchdog
│   ├── admin_assignment.py          # Balanced admin assignment engine + ORM models
│   ├── dedup.py                     # Duplicate detection across main/dist/in-progress
│   └── models.py                    # ORM model registration on NekoFetch's Base.metadata
│
├── bots/                            # ── The four anime-character bots ──
│   ├── lelouch/                     # 🎭 Code Geass — Request Bot
│   │   ├── app.py                   # Bot builder: /start, /help, /myrequests, /admin, /settings
│   │   └── handlers/
│   │       └── requests.py          # AniList search + dedup + admin assignment (reuses NekoFetch)
│   ├── levi/                        # ⚔️ Attack on Titan — Downloader Bot
│   │   ├── app.py                   # Bot builder: /start, /tasks, /sources, /header, /settings
│   │   └── handlers/
│   │       └── tasks.py             # Source selection + download queuing + thumbnail + header gen
│   ├── senku/                       # 🧪 Dr. Stone — Distribution Bot
│   │   ├── app.py                   # Bot builder: /start, /tasks, /create, /generate, /settings
│   │   └── handlers/
│   │       └── tasks.py             # Channel wizard + content generation via BotContentService
│   └── gojo/                        # 🔮 Jujutsu Kaisen — Publisher Bot
│       ├── app.py                   # Bot builder: /start, /tasks, /publish, /recover, /schedule
│       └── handlers/
│           └── tasks.py             # Review/publish flow + caption editing + channel recovery
│
├── nekofetch/                       # NekoFetch vendored (shared codebase — no duplicate code)
│   ├── bots/                        # Pyrogram clients: admin, distribution, FSM, middleware
│   ├── core/                        # DI container, config, logging, exceptions, security
│   ├── domain/                      # Enums: RequestStatus, JobStatus, DownloadScope, Role…
│   ├── infrastructure/              # PostgreSQL (SQLAlchemy 2 async), MongoDB (Motor), Redis
│   ├── providers/                   # TMDB, AcuteBot, Catbox, Telegraph, shortlinks
│   ├── services/                    # 40+ business services (request, queue, download, publish…)
│   ├── sources/                     # 6 extraction plugins (AniKoto, KAA, AniZone, Nyaa, TG, Local)
│   ├── ui/                          # Screens, components, progress bars, typography, artwork
│   └── localization/                # i18n (en.json, safe-format, auto-reload)
│
├── tests/                           # ── 291 tests, 100% passing ──
│   ├── conftest.py                  # Dual-backend fixtures (SQLite + PostgreSQL)
│   ├── helpers.py                   # Test factories (users, requests, bots, admins…)
│   ├── test_dedup.py                # 42 tests — duplicate detection
│   ├── test_admin_assignment.py     # 34 tests — admin assignment engine
│   ├── test_pipeline_manager.py     # 18 tests — pipeline lifecycle
│   ├── test_bot_handlers.py         # 10 tests — request handler logic
│   ├── test_edge_cases.py           # 7 tests — concurrency & race conditions
│   ├── test_integration.py          # 15 tests — cross-module integration
│   ├── test_models.py               # 8 tests — ORM model registration
│   └── test_kage_imports.py         # 6 tests — import validation
│
├── resources/                       # Canonical names, language files
├── migrations/                      # Alembic (shared with NekoFetch)
└── alembic.ini
```

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🧰 Tech Stack

| Concern | Choice |
|:-------:|:-------|
| Telegram | **Pyrogram (pyrofork)** |
| Language | **Python 3.12+**, fully `async` |
| Relational DB | **PostgreSQL** via **SQLAlchemy 2** (async) + **Alembic** |
| Document DB | **MongoDB** via **Motor** (shared with NekoFetch) |
| Cache / Live State | **Redis** (FSM state, rate limits, progress) |
| Scheduling | **APScheduler** |
| Config / Validation | **Pydantic v2** + pydantic-settings + YAML |
| HTTP | **httpx** (async, HTTP/2) |
| Logging | **structlog** |
| Lint / Tests | **ruff** · **pytest** (+ asyncio) |

<div align="center">

<br />

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)

</div>

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 📖 Glossary

| Term | Meaning |
|:-----|:--------|
| **Kuro Sōden** | 黒送伝 — "Black Transmission." The project name. The bots are invisible stagehands relaying work through the pipeline. |
| **Pipeline Stage** | One of four stages: `lelouch` (request), `levi` (download), `senku` (distribution), `gojo` (publishing) |
| **Admin Assignment** | The balanced scoring engine that picks the best available admin for a task |
| **Dedup** | Duplicate detection — checking main channel, distribution bots, and in-progress requests before accepting |
| **Relay** | The pattern of bots passing work forward through shared database state transitions |
| **Connection Watchdog** | Background task that detects dead Telegram links and force-reconnects |
| **FSM** | Finite State Machine — Redis-backed conversation state for multi-step admin flows |
| **Pipeline Manager** | `PipelineManager` — starts, supervises, and health-checks all four bots on one event loop |

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

<div align="center">

<br />

```
  ██╗  ██╗██╗   ██╗██████╗  ██████╗     ███████╗ ██████╗ ██████╗ ███████╗███╗   ██╗
  ██║ ██╔╝██║   ██║██╔══██╗██╔═══██╗    ██╔════╝██╔═══██╗██╔══██╗██╔════╝████╗  ██║
  █████╔╝ ██║   ██║██████╔╝██║   ██║    ███████╗██║   ██║██║  ██║█████╗  ██╔██╗ ██║
  ██╔═██╗ ██║   ██║██╔══██╗██║   ██║    ╚════██║██║   ██║██║  ██║██╔══╝  ██║╚██╗██║
  ██║  ██╗╚██████╔╝██║  ██║╚██████╔╝    ███████║╚██████╔╝██████╔╝███████╗██║ ╚████║
  ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝     ╚══════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝
```

*The dark relay behind NekoFetch. Four bots. One pipeline. Zero silent failures.*

<br />

**291 tests** · **4 bots** · **2 ORM tables** · **1 PipelineManager** · **30+ admins** · **one unbroken chain**

<br />

[![Made with ❤️](https://img.shields.io/badge/Made%20with-%E2%9D%A4-EC4899?style=for-the-badge)](#)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

🖤

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:16213e,50:1a1a2e,100:0d0d0d&height=120&section=footer" width="100%" alt="footer" />

</div>
