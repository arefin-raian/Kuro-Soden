<a id="readme-top"></a>

<!-- ╔══════════════════════════════════════════════════════════════════════════╗ -->
<!-- ║                       Kuro Sōden · 黒送伝 · README                       ║ -->
<!-- ╚══════════════════════════════════════════════════════════════════════════╝ -->

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d0d0d,50:1a1a2e,100:16213e&height=220&section=header&text=Kuro%20S%C5%8Dden&fontSize=72&fontColor=e0e0e0&animation=fadeIn&fontAlignY=38&desc=%E9%BB%92%E9%80%81%E4%BC%9D%20%E2%80%94%20Four-Bot%20Anime%20Distribution%20Relay&descAlignY=60&descSize=18" width="100%" alt="Kuro Sōden banner" />

# 🖤 Kuro Sōden (黒送伝)

### The Dark Relay — Four Anime-Themed Bot Pipeline for NekoFetch

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=18&duration=2800&pause=800&color=8B5CF6&center=true&vCenter=true&width=860&lines=Lelouch+requests+%E2%86%92+Levi+downloads+%E2%86%92+Senku+distributes+%E2%86%92+Gojo+publishes;Every+admin+assigned.+Every+duplicate+caught.+Every+step+observed.;291+tests.+Zero+silent+failures.+One+unbroken+chain." />

<br /><br />

<!-- ── status / tech row ─────────────────────────────────────── -->
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://mongodb.com)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-2.x-ff69b4?style=for-the-badge&logo=telegram&logoColor=white)](https://github.com/Mayuri-Chan/pyrofork)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)](https://sqlalchemy.org)

<!-- ── meta row ─────────────────────────────────────────────── -->
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge&logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-291%20passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![Async](https://img.shields.io/badge/Async-first-000000?style=for-the-badge&logo=asyncio&logoColor=white)](#-architecture)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](#-deploy-with-docker)
[![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black)](https://github.com/astral-sh/ruff)

<br />

<p>
  <a href="#-what-is-kuro-sōden"><b>What & Why</b></a> ·
  <a href="#-the-four-bots"><b>The Four Bots</b></a> ·
  <a href="#-the-pipeline"><b>Pipeline</b></a> ·
  <a href="#-admin-assignment-engine"><b>Admin Engine</b></a> ·
  <a href="#-duplicate-detection"><b>Dedup</b></a> ·
  <a href="#-deployment"><b>Deploy</b></a> ·
  <a href="#-project-layout"><b>Layout</b></a>
</p>

<br />

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   🎭 Lelouch           ⚔️ Levi            🧪 Senku           🔮 Gojo        ║
║   ────────────         ─────────          ────────────        ──────────      ║
║   Request Intake  →    Download      →    Distribution    →   Publishing      ║
║   Dedup Check          Source Select      Channel Create      Main Channel    ║
║   Admin Assign         Process Files      Content Generate    Index Update    ║
║   Management           Thumbnails         Stickers/Footer     Recovery        ║
║                                                                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

</div>

---

## ⚡ 30-Second Quick Start

```bash
git clone <repo-url> kuro-soden && cd kuro-soden
cp .env.example .env                        # fill in tokens + DB URLs
pip install -e ".[dev]"                     # editable install + pytest
python main.py                              # boots all 4 bots
```

You should see the build stamp:

```
  Kuro Sōden 0.1.0  ·  build 1d4389e  2026-07-14 22:00 UTC  ·  4-bot pipeline
```

> [!IMPORTANT]
> **Use that stamp to confirm a restart loaded new code.** If the commit hash isn't what you expect, the old process is likely still running.

---

<details open>
<summary><b>📑 Table of Contents</b></summary>

<br />

**Foundations**
- [⚡ 30-Second Quick Start](#-30-second-quick-start)
- [🖤 What is Kuro Sōden?](#-what-is-kuro-sōden)
- [💡 Why It Exists](#-why-it-exists)
- [✨ Feature Matrix](#-feature-matrix)

**The Pipeline**
- [🤖 The Four Bots](#-the-four-bots)
- [🔄 The Pipeline](#-the-pipeline)
- [👥 Admin Assignment Engine](#-admin-assignment-engine)
- [🛡️ Duplicate Detection](#-duplicate-detection)

**Run & Deploy**
- [🚀 Deployment](#-deployment)
  - [Pre-flight](#0-pre-flight-before-any-platform)
  - [Local (Linux / macOS / Windows)](#1-local-bare-metal-development--production)
  - [Docker](#2-deploy-with-docker)
  - [Docker Compose](#3-deploy-with-docker-compose)
  - [Railway](#4-deploy-on-railway)
  - [Render](#5-deploy-on-render)
  - [Koyeb](#6-deploy-on-koyeb)
  - [Linux VPS](#7-deploy-on-a-linux-vps--vm)
  - [Android / Termux / Cluterms](#8-run-on-android-termux--cluterms)
- [🔑 Environment Variables](#-environment-variables)
- [⚙️ Configuration](#-configuration)
- [📋 Commands Reference](#-commands-reference)

**Reference**
- [🏗️ Architecture](#-architecture)
- [🧪 Testing](#-testing)
- [📁 Project Layout](#-project-layout)
- [🧰 Tech Stack](#-tech-stack)
- [🗺️ Roadmap](#-roadmap)
- [🛠️ Troubleshooting](#-troubleshooting)
- [📖 Glossary](#-glossary)

</details>

---

## 🖤 What is Kuro Sōden?

**Kuro Sōden** (黒送伝 — *Black Transmission* / *Dark Relay*) is the **multi-bot pipeline orchestration layer** for NekoFetch. Instead of one giant bot handling every step of the anime lifecycle, Kuro Sōden splits the workflow into **four specialized Telegram bots** that form a relay chain — each bot responsible for one pipeline stage, each passing work to the next through shared database state.

The name comes from:

- **黒** (*Kuro*) — Black. Like the kabuki stagehands who dress in black and move invisibly behind the main performance. The bots work unseen.
- **送伝** (*Sōden*) — Transmission / Relay. Each bot receives work, processes its stage, and transmits it forward.

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
|:--------:|:-------|:------|:--------|
| 1 | **Main Channel** | `ChannelPost` by `anime_doc_id` | Already published → "available in the main channel!" |
| 2 | **Distribution Bot** | `DistributionBot` by `anime_doc_id`, enabled only | Available via bot → "via @bot_username!" |
| 3 | **In-Progress** | `Request` by `anime_doc_id` or `title ILIKE`, status in active set | Being processed → "REQ-XXXX is {downloading/processing/etc.}" |

> [!NOTE]
> **Priority matters.** Main channel is checked first — if an anime is published AND has a distribution bot, the user gets the main channel link (the most direct access). Distribution is checked before in-progress so users aren't told "it's being processed" when it's actually already available.

In-progress detection uses a defined set of active statuses (`PENDING`, `APPROVED`, `QUEUED`, `DOWNLOADING`, `PROCESSING`, `READY`). Published, failed, and rejected requests are excluded.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🚀 Deployment

Kuro Sōden is **standalone**: NekoFetch's source is vendored under `nekofetch/`, so the only hard requirements are Python 3.12+ and the three data stores (PostgreSQL, MongoDB, Redis). You can run it locally, in Docker, or on any platform that gives you a long-running container and persistent storage.

> [!IMPORTANT]
> **You need 4 separate Telegram bot tokens** (one per pipeline bot) plus the shared `ADMIN_BOT_TOKEN`. Create them all with [@BotFather](https://t.me/BotFather). Each token must be the single `<id>:<token>` string — do not paste the same token twice.

### 0. Pre-flight (before any platform)

1. Create a Telegram app at [https://my.telegram.org](https://my.telegram.org) and copy `api_id` + `api_hash`.
2. Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your personal user id.
3. Create 4 bots with [@BotFather](https://t.me/BotFather):
   - `Lelouch Request Bot`
   - `Levi Downloader Bot`
   - `Senku Distribution Bot`
   - `Gojo Publisher Bot`
4. Decide how you will host Postgres, MongoDB, and Redis.
   - Free tiers: [Neon](https://neon.tech), [supabase.com](https://supabase.com) (Postgres), [MongoDB Atlas M0](https://mongodb.com/atlas), [Redis Labs](https://redis.com/try-free/) / [Upstash Redis](https://upstash.com).
   - Self-hosting: Docker image or system packages.
5. `cp .env.example .env` and fill in values. See [Environment Variables](#-environment-variables) for a full reference.

### 1. Local (bare-metal) — Development / Production

#### Linux / macOS

```bash
# 1. Ensure Python 3.12+
python3 --version          # must be >= 3.12

# 2. Clone the repo
git clone <repo-url> kuro-soden
cd kuro-soden

# 3. Install system dependencies
# Debian / Ubuntu
sudo apt-get update && sudo apt-get install -y ffmpeg mkvtoolnix curl

# macOS (Homebrew)
brew install ffmpeg mkvtoolnix curl

# 4. Configure
# Or edit the included .env.example then copy:
cp .env.example .env
nano .env

# 5. Create a venv and install
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# 6. Run
python main.py
```

#### Windows

```powershell
# 0. Install Python 3.12+ and ffmpeg/mkvtoolnix binaries, then add them to PATH.
# 1. Clone
git clone <repo-url> kuro-soden
cd kuro-soden

# 2. Copy and edit .env
copy .env.example .env
notepad .env

# 3. Create venv and install
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

# 4. Run
python main.py
```

> [!TIP]
> Use the convenience launchers on first run:
> - Linux/macOS: `bash run.sh`
> - Windows: double-click `run.bat` or run `run.bat` in a terminal.
> Both scripts create the venv, install dependencies, and start the pipeline.

### 2. Deploy with Docker

The included `Dockerfile` builds a fully self-contained image with Python 3.12, ffmpeg, mkvtoolnix, and Playwright Chromium. No Docker Compose is required; the container expects Postgres / MongoDB / Redis to be reachable via your `.env`.

```bash
# Build
docker build -t kuro-soden:latest .

# Run (mount your .env and a persistent volume for storage/sessions)
docker run -d \
  --name kuro-soden \
  --env-file .env \
  -v kuro-soden-data:/data \
  kuro-soden:latest

# Watch logs
docker logs -f kuro-soden
```

> [!CAUTION]
> Telegram session files live inside `data/sessions`. If you re-create the container without mounting a persistent volume, the bots will have to re-authenticate and any queued work stored locally may disappear.

### 3. Deploy with Docker Compose

Save this next to the repo as `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-kuro_soden}
      POSTGRES_USER: ${POSTGRES_USER:-kuro_soden}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change-me}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"

  mongo:
    image: mongo:7
    restart: unless-stopped
    volumes:
      - mongo_data:/data/db
    ports:
      - "127.0.0.1:27017:27017"

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"

  kuro-soden:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      MONGO_URI: mongodb://mongo:27017
      REDIS_URL: redis://redis:6379/0
      STORAGE_PATH: /data/storage
      SESSION_PATH: /data/sessions
    volumes:
      - kuro_soden_data:/data
    depends_on:
      - postgres
      - mongo
      - redis

volumes:
  postgres_data:
  mongo_data:
  kuro_soden_data:
```

Then:

```bash
# Configure .env first, leaving DB variables as defaults (Compose overrides them)
cp .env.example .env
nano .env

# Start the whole stack
docker compose up -d

# Watch logs
docker compose logs -f kuro-soden

# Run migrations once schema is stable
docker compose exec kuro-soden alembic upgrade head

# Restart after code changes
docker compose down
docker compose up --build -d
```

### 4. Deploy on Railway

Railway gives you a Git-connected deployment with managed Postgres/Redis add-ons. MongoDB can come from MongoDB Atlas or Railway's community template.

#### Option A: New Railway project from this repo

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login and create project
railway login
railway init --name kuro-soden

# 3. Add PostgreSQL and Redis services through the Railway dashboard
#    Railway will inject their connection URLs automatically.

# 4. Add a MongoDB service (e.g., MongoDB Atlas or a Railway MongoDB template)
#    Copy the MONGO_URI from Atlas.

# 5. Add the Kuro Sōden service by linking this repo and push
railway link

# 6. Set every secret from .env.example
cat .env.example | while IFS='' read -r line || [ -n "$line" ]; do
    key=$(echo "$line" | cut -d '=' -f 1)
    case "$key" in
        "#"* | "") continue ;;
    esac
    railway variables set "$key="
done

# 7. Add a 10 GB persistent volume mounted at /data

# 8. Deploy
railway up
```

#### Option B: Nixpack/Railway `railway.json`

Create `railway.json` if the platform isn't auto-detecting your start command:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "startCommand": "python main.py",
    "healthcheckPath": "/",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

> [!IMPORTANT]
> Kuro Sōden is a **worker**, not a web server. Railway's default healthchecks on port 8000 will fail unless you expose a lightweight HTTP server. For pure Telegram bots, disable the healthcheck or switch to a `worker` service without a public domain.

### 5. Deploy on Render

A `render.yaml` blueprint is already included in the repo.

1. Push the repo to GitHub / GitLab.
2. In the Render dashboard, click **New + → Blueprint**.
3. Paste your repo URL and select `render.yaml`.
4. Fill in the synchronized environment variables (`TELEGRAM_API_ID`, tokens, DB URLs, etc.) in the Render dashboard.
5. The blueprint creates:
   - A **Background Worker** service (`kuro-soden`) running `python main.py`.
   - A **10 GB disk** mounted at `/data/storage` for persistent storage.
6. Click **Apply** and wait for the service to turn **Live**.

```bash
# Render also has a CLI
curl https://render.com/install.sh | bash
render login
render blueprint apply
```

> [!TIP]
> Render's free tier spins the worker down after 15 minutes of inactivity. For a 24/7 Telegram bot, use a paid instance type or pair Render with a cron ping. Alternatively use a separate `render.yaml` with `plan: standard`.

### 6. Deploy on Koyeb

Koyeb accepts Docker builds straight from a Git repo or a pushed image on a registry.

#### Option A: Git-driven Docker deploy

```bash
# 1. Install Koyeb CLI
koyeb --help || curl -fsSL https://raw.githubusercontent.com/koyeb/koyeb-cli/main/install.sh | bash

# 2. Login (creates API token in browser)
koyeb login

# 3. Create the app and service
APP_NAME=kuro-soden
SERVICE_NAME=kuro-soden-worker

koyeb app create $APP_NAME

koyeb service create $SERVICE_NAME \
  --app $APP_NAME \
  --docker <your-dockerhub-username>/kuro-soden:latest \
  --instance-type nano \
  --env PORT=8000 \
  --env PYTHONUNBUFFERED=1 \
  --env TELEGRAM_API_ID=<id> \
  --env TELEGRAM_API_HASH=<hash> \
  --env REQUEST_BOT_TOKEN=<token> \
  --env DOWNLOADER_BOT_TOKEN=<token> \
  --env DISTRIBUTION_BOT_TOKEN=<token> \
  --env PUBLISHER_BOT_TOKEN=<token> \
  --env ADMIN_BOT_TOKEN=<token> \
  --env ADMIN_IDS=<id> \
  --env OWNER_ID=<id> \
  --env SECRET_KEY=<secret> \
  --env POSTGRES_HOST=<host> \
  --env POSTGRES_PASSWORD=<pass> \
  --env MONGO_URI=<uri> \
  --env REDIS_URL=<url> \
  --env STORAGE_PATH=/data/storage \
  --env SESSION_PATH=/data/sessions \
  --port 8000:HTTP \
  --volume /data:10

koyeb service update $APP_NAME/$SERVICE_NAME --min-scale 1 --max-scale 1
```

#### Option B: koyeb.yaml manifest

Create `koyeb.yaml`:

```yaml
name: kuro-soden-worker
app_name: kuro-soden
source:
  type: git
  git:
    branch: main
builder:
  type: dockerfile
ports:
  - port: 8000
    protocol: http
env:
  PYTHONUNBUFFERED: "1"
  PYTHONPATH: /app
  REQUEST_BOT_TOKEN: ${REQUEST_BOT_TOKEN}
  DOWNLOADER_BOT_TOKEN: ${DOWNLOADER_BOT_TOKEN}
  DISTRIBUTION_BOT_TOKEN: ${DISTRIBUTION_BOT_TOKEN}
  PUBLISHER_BOT_TOKEN: ${PUBLISHER_BOT_TOKEN}
  ADMIN_BOT_TOKEN: ${ADMIN_BOT_TOKEN}
  TELEGRAM_API_ID: ${TELEGRAM_API_ID}
  TELEGRAM_API_HASH: ${TELEGRAM_API_HASH}
  ADMIN_IDS: ${ADMIN_IDS}
  OWNER_ID: ${OWNER_ID}
  SECRET_KEY: ${SECRET_KEY}
  MONGO_URI: ${MONGO_URI}
  REDIS_URL: ${REDIS_URL}
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  STORAGE_PATH: /data/storage
  SESSION_PATH: /data/sessions
volumes:
  - path: /data
    size: 10
```

Then:

```bash
koyeb app create kuro-soden
koyeb service create kuro-soden-worker --app kuro-soden --config koyeb.yaml
```

> [!NOTE]
> Koyeb's smallest persistent storage is 10 GB. If you choose a region without volume support, store sessions on an external Postgres-backed state instead (not recommended for active Pyrogram sessions).

### 7. Deploy on a Linux VPS / VM

For full control, run it as a systemd service on any Debian/Ubuntu/RHEL server.

```bash
# 1. Update and install dependencies
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev git \
     ffmpeg mkvtoolnix redis-server postgresql postgresql-contrib

# 2. Install MongoDB separately or use Atlas
#    See https://docs.mongodb.com/manual/tutorial/install-mongodb-on-ubuntu/

# 3. Clone and install
cd /opt
sudo git clone <repo-url> kuro-soden
sudo chown -R $USER:$USER kuro-soden
cd kuro-soden
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 4. Configure
cp .env.example .env
nano .env

# 5. Create databases
sudo -u postgres psql -c "CREATE USER kuro_soden WITH PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE kuro_soden OWNER kuro_soden;"
```

#### systemd unit

Create `/etc/systemd/system/kuro-soden.service` (run as root):

```ini
[Unit]
Description=Kuro Sōden 4-Bot Pipeline
After=network.target postgresql.service redis.service mongod.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/kuro-soden
Environment=PATH=/opt/kuro-soden/.venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/opt/kuro-soden/.env
ExecStart=/opt/kuro-soden/.venv/bin/python /opt/kuro-soden/main.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kuro-soden
sudo systemctl status kuro-soden
sudo journalctl -u kuro-soden -f
```

### 8. Run on Android (Termux / Cluterms)

You can run Kuro Sōden directly on Android using [Termux](https://termux.dev) or any terminal emulator that provides a full Linux environment (Cluterms, Alpine Term, UserLAnd). This is best for low-traffic testing, not production.

#### Termux (recommended)

```bash
# 1. Install Termux from F-Droid (not the Play Store version)
#    https://f-droid.org/packages/com.termux/

# 2. Update packages and install requirements
pkg update
pkg install -y python git ffmpeg postgresql redis

# 3. Start local data stores in separate Termux sessions
pg_ctl -D $PREFIX/var/lib/postgresql start
redis-server --daemonize yes

# 4. Clone and install
cd $HOME
git clone <repo-url> kuro-soden
cd kuro-soden
pip install -e ".[dev]"

# 5. Configure .env for local connections
cat > .env <<EOF
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=your_hash
REQUEST_BOT_TOKEN=...
DOWNLOADER_BOT_TOKEN=...
DISTRIBUTION_BOT_TOKEN=...
PUBLISHER_BOT_TOKEN=...
ADMIN_BOT_TOKEN=...
ADMIN_IDS=...
OWNER_ID=...
SECRET_KEY=...
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=kuro_soden
POSTGRES_PASSWORD=...
POSTGRES_DB=kuro_soden
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB=kuro_soden
REDIS_URL=redis://127.0.0.1:6379/0
STORAGE_PATH=data/storage
SESSION_PATH=data/sessions
EOF

# 6. Run
python main.py
```

> [!WARNING]
> Android kills background processes aggressively. Use `termux-wake-lock`, run inside `tmux` or `screen`, and disable battery optimization for Termux. For production use, move to Render/Railway/Koyeb/a VPS.

#### Cluterms / other proot distros

If you run a Debian/Ubuntu chroot inside Android (via `proot-distro` or `Andronix`):

```bash
proot-distro install debian
proot-distro login debian
# Now follow the "Linux VPS" instructions from inside the chroot.
```

---

## 🔑 Environment Variables

| Variable | Bot | Required | Description |
|----------|-----|:--------:|:------------|
| `TELEGRAM_API_ID` | all | ✅ | API id from [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | all | ✅ | API hash from [my.telegram.org](https://my.telegram.org) |
| `REQUEST_BOT_TOKEN` | 🎭 Lelouch | ✅ | BotFather token for the request bot |
| `DOWNLOADER_BOT_TOKEN` | ⚔️ Levi | ✅ | BotFather token for the downloader bot |
| `DISTRIBUTION_BOT_TOKEN` | 🧪 Senku | ✅ | BotFather token for the distribution bot |
| `PUBLISHER_BOT_TOKEN` | 🔮 Gojo | ✅ | BotFather token for the publisher bot |
| `ADMIN_BOT_TOKEN` | — | ✅ | NekoFetch admin bot token (used by nekofetch services) |
| `ADMIN_IDS` | — | ✅ | Comma-separated Telegram user IDs with admin rights |
| `OWNER_ID` | — | ✅ | Telegram user ID of the bot owner |
| `SECRET_KEY` | — | ✅ | Fernet key for encryption. Generate with Python (see below) |
| `POSTGRES_HOST` | — | ✅ | PostgreSQL host |
| `POSTGRES_PORT` | — | ✅ | PostgreSQL port (default `5432`) |
| `POSTGRES_USER` | — | ✅ | PostgreSQL user |
| `POSTGRES_PASSWORD` | — | ✅ | PostgreSQL password |
| `POSTGRES_DB` | — | ✅ | PostgreSQL database name |
| `MONGO_URI` | — | ✅ | MongoDB connection URI |
| `MONGO_DB` | — | ✅ | MongoDB database name |
| `REDIS_URL` | — | ✅ | Redis URL, e.g. `redis://localhost:6379/0` |
| `STORAGE_PATH` | — | ✅ | Local path for downloads/thumbnails |
| `SESSION_PATH` | — | ✅ | Local path for Pyrogram session files |
| `TMDB_API_READ_ACCESS_TOKEN` | — | ⚠️ | TMDB read token; needed for poster/artwork enrichment |
| `TMDB_API_KEY` | — | ⚠️ | TMDB API key (v3) |
| `LOG_LEVEL` | all | ❌ | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |
| `LOG_JSON` | all | ❌ | `true`/`false` (default `false`) |
| `AUTO_CREATE_SCHEMA` | — | ❌ | `true` (dev) or `false` (production with Alembic) |

Generate a `SECRET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> [!IMPORTANT]
> Never commit `.env`. It is already gitignored, but double-check with `git status` before pushing.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## ⚙️ Configuration

Behaviour lives in `config.yaml`. Most values can also be overridden at runtime from the admin settings panel (stored in MongoDB).

### Handy sections to review before going live

| Section | What it controls |
|:--------|:-----------------|
| `features` | Master toggles: request system, downloads, distribution bots, analytics, etc. |
| `downloads` | Concurrent downloads, retries, chunk size |
| `processing` | Verify / rename / metadata / branding / thumbnail toggles |
| `branding` | Channel name, footer text, watermark, metadata comment |
| `storage_channel` | Database channel for ordered content packs |
| `main_channel` | Public channel where published anime appear |
| `index_channel` | A–Z index channel |
| `log_channel` | Live event feed + pinned dashboard |
| `thumbnail_channel` | Custom thumbnail approval gallery |
| `bot` | Username suffixes, max bots/channels per account |

See `docs/DEPLOYMENT.md` for a first-run checklist covering log channels, storage channels, distribution bots, and the main/index setup.

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

## 🏗️ Architecture

Kuro Sōden runs as a standalone Python project with NekoFetch vendored inside (`nekofetch/`). All four bots share NekoFetch's DI container, database sessions, Redis cache, and configuration — **zero code duplication**.

```
                        ┌──────────────────────────────────────────────┐
  Telegram users  ◄────►│  KURO SŌDEN BOTS  (4 Pyrogram clients)       │
  Staff / admins  ◄────►│  Lelouch · Levi · Senku · Gojo               │
                         │  Each: handlers → callback routing → FSM     │
                         └───────────────────┬──────────────────────────┘
                                             │ calls
                         ┌───────────────────▼────────────────────────────┐
                         │  NEKOFETCH SERVICES  (reused — no rewrite)     │
                         │  RequestService · QueueService · DownloadWorker│
                         │  BotContentService · PublishingService · etc.  │
                         │  BotFactory · BotOrchestrator · FranchiseFlow  │
                         └───────┬────────────────────────┬───────────────┘
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

## 🧪 Testing

```bash
# Run all 291 tests against an in-memory SQLite database (fast — no external deps)
python -m pytest tests/ -q

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

**291 tests, 100% passing** — on both SQLite (fast local dev) and PostgreSQL (production parity).

> [!NOTE]
> **Both backends supported.** The test suite uses an in-memory SQLite database by default (no external dependencies needed). Set `KAGE_TEST_DATABASE_URL` to run against a real PostgreSQL instance — all 291 tests pass on both. SQLite-specific SQL has been replaced with DB-agnostic ORM introspection.

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 📁 Project Layout

```
.
├── main.py                          # Entry point — DI container → PipelineManager
├── config.yaml                      # Runtime behaviour (features, channels, branding)
├── pyproject.toml                   # Project metadata + dependencies
├── requirements.txt                 # Flat lock-style dependency list
├── README.md                        # You are here
├── LICENSE                          # MIT license
├── Dockerfile                       # Self-contained Docker image (Python 3.12)
├── render.yaml                      # Render blueprint (worker + 10 GB disk)
├── run.sh                           # Linux/macOS convenience launcher
├── run.bat                          # Windows convenience launcher
├── .env.example                     # All required environment variables
│
├── shared/                          # ── Kuro Sōden shared layer ──
│   ├── __init__.py
│   ├── pipeline_manager.py          # Starts & supervises all 4 bots + watchdog
│   ├── admin_assignment.py          # Balanced admin assignment engine + ORM models
│   ├── dedup.py                     # Duplicate detection across main/dist/in-progress
│   ├── models.py                    # ORM model re-exports
│   ├── request_gate.py              # Request validation helpers
│   ├── menu_router.py               # Inline menu/callback routing
│   ├── settings_content.py          # Settings UI builder
│   └── ui_helpers.py                # Shared Telegram UI helpers
│
├── bots/                            # ── The four anime-character bots ──
│   ├── __init__.py
│   ├── lelouch/                     # 🎭 Code Geass — Request Bot
│   │   ├── __init__.py
│   │   ├── app.py
│   │   └── handlers/
│   │       ├── __init__.py
│   │       └── requests.py
│   ├── levi/                        # ⚔️ Attack on Titan — Downloader Bot
│   │   ├── __init__.py
│   │   ├── app.py
│   │   └── handlers/
│   │       ├── __init__.py
│   │       └── tasks.py
│   ├── senku/                       # 🧪 Dr. Stone — Distribution Bot
│   │   ├── __init__.py
│   │   ├── app.py
│   │   └── handlers/
│   │       ├── __init__.py
│   │       └── tasks.py
│   └── gojo/                        # 🔮 Jujutsu Kaisen — Publisher Bot
│       ├── __init__.py
│       ├── app.py
│       └── handlers/
│           ├── __init__.py
│           └── tasks.py
│
├── nekofetch/                       # NekoFetch vendored (shared codebase — no duplicate code)
│   ├── __init__.py
│   ├── __main__.py
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
│   ├── __init__.py
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
├── migrations/                      # Alembic migrations (shared schema)
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── resources/                       # Canonical names, language files
│   ├── canonical_names.json
│   └── language/
│       └── en.json
│
├── docs/                            # Living project documentation
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── SCRAPER_GUIDE.md
│   ├── PROJECT_JOURNAL.md
│   └── TASKS.md
│
├── playground/                      # Prototypes / diagnostic scripts
│   ├── probe_acutebot.py
│   └── diag_tap_response.py
│
├── thumbnail/                       # Thumbnail assets
│   ├── index.html
│   ├── logo.png
│   ├── thumb.svg
│   └── ...
│
├── images/                          # Reference artwork
│   └── ... (anime character artwork)
│
└── data/                            # Created at runtime
    ├── storage/                     # Downloads, thumbnails, artifacts
    └── sessions/                    # Pyrogram .session files
```

> [!NOTE]
> The codebase imports itself using the `kurosoden` namespace (`kurosoden.bots.lelouch.app`, etc.). `main.py` registers a lightweight module shim at startup so those imports resolve to the real `bots/`, `shared/`, and `nekofetch/` directories at the repo root. This keeps the project unpackable anywhere (`/app`, `/opt/kuro-soden`, your home dir, or a Render/Railway volume) without editing source paths.

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
| Media | **ffmpeg** · **mkvtoolnix** · **Pillow** · **Playwright** |

<div align="center">

<br />

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=for-the-badge&logo=mongodb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

</div>

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🗺️ Roadmap

| Status | Feature |
|:------:|:--------|
| ✅ | 4-bot relay pipeline with shared DB state |
| ✅ | Balanced admin assignment engine with row-level locking |
| ✅ | Three-layer duplicate detection |
| ✅ | Connection watchdog + auto-reconnect |
| ✅ | 291-test suite on SQLite & PostgreSQL |
| ✅ | Docker + Render blueprint |
| 🚧 | Scheduled publishing command |
| 🚧 | Web dashboard for admin workload |
| 💡 | Multi-region deployment notes (fly.io, AWS ECS) |

<p align="right">(<a href="#readme-top">▲ back to top</a>)</p>

---

## 🛠️ Troubleshooting

| Symptom | Likely cause | Fix |
|:--------|:-------------|:----|
| Bot doesn't respond to `/start` | Wrong token or DBs not reachable | Check logs, verify `ADMIN_BOT_TOKEN` / Postgres / MongoDB / Redis |
| No Admin Panel button | Your Telegram id isn't in `ADMIN_IDS` | Add it and restart |
| Log channel silent / no pins | Admin bot isn't a channel admin, or wrong `channel_id` | Re-add admin with post + edit + pin rights; verify channel id |
| Indexing/delivery fails | Admin bot isn't an admin of the storage channel, or bad message range | Check storage channel membership and pack range |
| Pipeline bot won't start | Missing `*_BOT_TOKEN` env var | Fill in the 4 pipeline tokens |
| "ACCESS_TOKEN_INVALID" on startup | Token was pasted twice or is otherwise malformed | Copy the exact string from [@BotFather](https://t.me/BotFather) |
| Build stamp git hash is wrong / old | Previous process still running | `pkill -f main.py` then restart |
| Download worker never picks up job | Download queue feature disabled or worker not running | Set `features.download_queue: true`; run the queue worker if separate |
| Android process killed overnight | Battery optimization / Doze | `termux-wake-lock`, disable battery optimization, run in `tmux` |
| Render service sleeps | Free tier pauses after inactivity | Upgrade instance or add uptime ping |

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

**291 tests** · **4 bots** · **6 sources** · **2 ORM tables** · **1 PipelineManager** · **30+ admins** · **one unbroken chain**

<br />

[![License MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

🖤

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:16213e,50:1a1a2e,100:0d0d0d&height=120&section=footer" width="100%" alt="footer" />

</div>
