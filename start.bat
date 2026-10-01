@echo off
REM =============================================================================
REM UniversalDRM — One-Line Server Start & Deployment Script (Windows)
REM
REM Usage:
REM   start.bat              REM Start API server on http://0.0.0.0:8000
REM   start.bat view doc.pdf REM Start instant viewer on http://0.0.0.0:5050
REM =============================================================================

set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000

echo ==========================================================
echo    UniversalDRM -- Server Deployment Starting (Windows)
echo ==========================================================

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [-] Error: Python is not installed or not in your PATH.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [+] Creating virtual environment in .venv...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [+] Installing/updating dependencies...
pip install -q --upgrade pip
pip install -q -e .[api,demo]

if "%~1"=="" (
    echo [+] Starting UniversalDRM server...
    echo     --^> Open in browser: http://localhost:%PORT%
    echo     --^> Interactive Docs: http://localhost:%PORT%/docs
    python -m universal_drm.cli serve --host %HOST% --port %PORT%
) else (
    python -m universal_drm.cli %*
)
