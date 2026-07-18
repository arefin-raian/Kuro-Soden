#!/usr/bin/env bash
# ============================================================
#  Kuro Sōden — Userbot Session Manager (Linux / macOS)
#  Run:  bash add_userbot.sh
#  Add / list / remove the Telegram USER accounts the pipeline
#  logs in with. Reuses the same .venv as run.sh.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

VENV_PY=".venv/bin/python3"

# --- ensure a virtual environment exists --------------------
if [ ! -f "$VENV_PY" ]; then
    echo "[Kuro Sōden] No virtual environment found. Creating .venv ..."
    python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
    if [ ! -f "$VENV_PY" ]; then
        echo "[Kuro Sōden] ERROR: could not create a virtual environment."
        echo "[Kuro Sōden] Install Python 3.12+ from https://python.org and retry."
        exit 1
    fi
    echo "[Kuro Sōden] Installing dependencies ..."
    "$VENV_PY" -m pip install --upgrade pip -q
    "$VENV_PY" -m pip install -e .
fi

# --- sanity: secrets file -----------------------------------
if [ ! -f ".env" ]; then
    echo "[Kuro Sōden] ERROR: .env not found."
    echo "[Kuro Sōden] Copy .env.example to .env and fill in TELEGRAM_API_ID"
    echo "[Kuro Sōden] and TELEGRAM_API_HASH first, then re-run this."
    exit 1
fi

"$VENV_PY" scripts/userbot_manager.py
