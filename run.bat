@echo off
REM ============================================================
REM  Kuro Sōden launcher (Windows)
REM  Double-click this file, or run `run.bat` from a terminal.
REM  Creates the venv + installs deps on first run, then boots
REM  all four pipeline bots (Lelouch, Levi, Senku, Gojo).
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"

REM --- ensure a virtual environment exists --------------------
if not exist "%VENV_PY%" (
    echo [Kuro Sōden] No virtual environment found. Creating .venv ...
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
    if not exist "%VENV_PY%" (
        echo [Kuro Sōden] ERROR: could not create a virtual environment.
        echo [Kuro Sōden] Install Python 3.12+ from https://python.org and retry.
        pause
        exit /b 1
    )
)

REM --- ensure deps are installed ------------------------------
echo [Kuro Sōden] Syncing dependencies ...
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install -e .
if errorlevel 1 (
    echo [Kuro Sōden] ERROR: dependency install failed. See the output above.
    pause
    exit /b 1
)

REM --- sanity: secrets file -----------------------------------
if not exist ".env" (
    echo [Kuro Sōden] WARNING: .env not found.
    echo [Kuro Sōden] Copy .env.example to .env and fill in your tokens:
    echo [Kuro Sōden]     copy .env.example .env
    echo.
)

REM --- run ----------------------------------------------------
echo [Kuro Sōden] Starting 4-bot pipeline...
echo [Kuro Sōden]   Lelouch    - Request intake
echo [Kuro Sōden]   Levi       - Download delegation
echo [Kuro Sōden]   Senku      - Distribution
echo [Kuro Sōden]   Gojo       - Publishing
echo.
echo [Kuro Sōden] Press Ctrl+C to stop.

set "PATH=%~dp0.venv\Scripts;%PATH%"
"%VENV_PY%" main.py

echo.
echo [Kuro Sōden] Process exited.
pause
