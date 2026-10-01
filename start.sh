#!/usr/bin/env bash
# =============================================================================
# UniversalDRM — One-Line Server Start & Deployment Script
#
# Usage:
#   ./start.sh              # Start API server on http://0.0.0.0:8000
#   ./start.sh view doc.pdf # Start instant viewer on http://0.0.0.0:5050
#   PORT=8080 ./start.sh    # Custom port
# =============================================================================
set -e

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "=========================================================="
echo "   UniversalDRM — One-Line Server Deployment Starting     "
echo "=========================================================="

# Check if Docker deployment is requested
if [ "$1" = "docker" ] || [ "${USE_DOCKER:-0}" = "1" ]; then
    shift || true
    echo "[+] Deploying with Docker Compose..."
    docker compose up -d api
    echo "[✓] UniversalDRM running via Docker on http://${HOST}:${PORT}"
    exit 0
fi

# Locate Python 3
if command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "[-] Error: Python 3.11+ is required but not installed." >&2
    exit 1
fi

# Verify Python version >= 3.11
$PY -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || {
    echo "[-] Error: Python 3.11 or newer is required." >&2
    exit 1
}

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
    echo "[+] Creating virtual environment in .venv..."
    $PY -m venv .venv
fi

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    # shellcheck disable=SC1091
    source .venv/Scripts/activate
fi

# Install dependencies if needed
echo "[+] Checking/installing dependencies..."
pip install -q --upgrade pip
pip install -q -e ".[api,demo]"

# Run CLI with any provided arguments, or default to starting the API server
if [ $# -gt 0 ]; then
    exec python -m universal_drm.cli "$@"
else
    echo "[✓] Starting UniversalDRM server on http://${HOST}:${PORT}..."
    exec python -m universal_drm.cli serve --host "${HOST}" --port "${PORT}"
fi
