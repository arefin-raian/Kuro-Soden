@echo off
REM Kuro Sōden launcher (Windows)
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [Kuro Sōden] No virtual environment found. Creating .venv ...
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
)

echo [Kuro Sōden] Syncing dependencies ...
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install -e .

if not exist ".env" (
    echo [Kuro Sōden] WARNING: .env not found. Copy .env.example to .env
)

echo [Kuro Sōden] Starting 4-bot pipeline...
set "PATH=%~dp0.venv\Scripts;%PATH%"

taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
if exist "data\sessions" (
    del /q "data\sessions\*.session-journal" 2>nul
    del /q "data\sessions\*.session-shm" 2>nul
    del /q "data\sessions\*.lock" 2>nul
)

"%VENV_PY%" main.py

echo.
echo [Kuro Sōden] Process exited.
pause
