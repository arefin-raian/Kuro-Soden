@echo off
REM ============================================================
REM  Kuro Soden - Userbot Session Manager (Windows)
REM  Double-click this file, or run `add_userbot.bat` from a
REM  terminal, to add / list / remove the Telegram USER accounts
REM  the pipeline logs in with. Reuses the same .venv as run.bat.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"

REM --- ensure a virtual environment exists --------------------
if not exist "%VENV_PY%" (
    echo [Kuro Soden] No virtual environment found. Creating .venv ...
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
    if not exist "%VENV_PY%" (
        echo [Kuro Soden] ERROR: could not create a virtual environment.
        echo [Kuro Soden] Install Python 3.12+ from https://python.org and retry.
        pause
        exit /b 1
    )
    echo [Kuro Soden] Installing dependencies ...
    "%VENV_PY%" -m pip install --upgrade pip -q
    "%VENV_PY%" -m pip install -e .
)

REM --- sanity: secrets file -----------------------------------
if not exist ".env" (
    echo [Kuro Soden] ERROR: .env not found.
    echo [Kuro Soden] Copy .env.example to .env and fill in TELEGRAM_API_ID
    echo [Kuro Soden] and TELEGRAM_API_HASH first, then re-run this.
    pause
    exit /b 1
)

set "PATH=%~dp0.venv\Scripts;%PATH%"
"%VENV_PY%" scripts\userbot_manager.py

echo.
pause
