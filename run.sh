#!/usr/bin/env bash
# ============================================================
#  Kuro Sōden launcher (Linux / macOS)
#  Run:  bash run.sh
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

VENV_PY=".venv/bin/python3"

if [ ! -f "$VENV_PY" ]; then
    echo "[Kuro Sōden] No virtual environment found. Creating .venv ..."
    python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
fi

echo "[Kuro Sōden] Syncing dependencies ..."
"$VENV_PY" -m pip install --upgrade pip -q
"$VENV_PY" -m pip install -e .

if [ ! -f ".env" ]; then
    echo "[Kuro Sōden] WARNING: .env not found. Copy .env.example to .env"
fi

echo "[Kuro Sōden] Starting 4-bot pipeline..."
export PATH="$(pwd)/.venv/bin:$PATH"

pkill -f "python.*main.py" 2>/dev/null || true
sleep 2
if [ -d "data/sessions" ]; then
    rm -f data/sessions/*.session-journal data/sessions/*.session-shm data/sessions/*.lock
fi

exec "$VENV_PY" main.py
