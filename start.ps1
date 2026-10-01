# =============================================================================
# UniversalDRM — PowerShell Server Start & Deployment Script
#
# Usage:
#   .\start.ps1              # Start API server on http://0.0.0.0:8000
#   .\start.ps1 view doc.pdf # Start instant viewer on http://0.0.0.0:5050
# =============================================================================
param(
    [string]$Command = "serve",
    [string]$TargetFile = "",
    [string]$HostIP = "0.0.0.0",
    [int]$Port = 8000
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   UniversalDRM -- Server Deployment Starting (PowerShell) " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Check Python availability
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[-] Error: Python is not installed or not found in PATH." -ForegroundColor Red
    exit 1
}

# If inside an existing virtual environment or Conda environment, use it
if (-not $env:VIRTUAL_ENV -and -not $env:CONDA_DEFAULT_ENV) {
    if (-not (Test-Path ".venv")) {
        Write-Host "[+] Creating virtual environment in .venv..." -ForegroundColor Yellow
        python -m venv .venv
    }
    Write-Host "[+] Activating .venv..." -ForegroundColor Yellow
    & .\.venv\Scripts\Activate.ps1
}

Write-Host "[+] Checking/installing dependencies..." -ForegroundColor Yellow
python -m pip install -q --upgrade pip
python -m pip install -q -e ".[api,demo]"

if ($Command -eq "view" -or ($Command -ne "serve" -and (Test-Path $Command))) {
    $filePath = if ($Command -eq "view") { $TargetFile } else { $Command }
    Write-Host "[+] Starting UniversalDRM Viewer for: $filePath" -ForegroundColor Green
    python -m universal_drm.cli view $filePath --host $HostIP --port 5050
} else {
    $displayHost = if ($HostIP -eq "0.0.0.0") { "localhost" } else { $HostIP }
    Write-Host "[+] UniversalDRM API server running!" -ForegroundColor Green
    Write-Host "    --> Open in browser: http://${displayHost}:${Port}" -ForegroundColor Cyan
    Write-Host "    --> API Docs:        http://${displayHost}:${Port}/docs" -ForegroundColor Cyan
    python -m universal_drm.cli serve --host $HostIP --port $Port
}
