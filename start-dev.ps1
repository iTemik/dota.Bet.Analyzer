# Start development environment: Redis, Celery, Backend, and Frontend
# Run: .\start-dev.ps1

Write-Host "Starting Dota Bet Analyzer Development Environment..." -ForegroundColor Green
Write-Host ""

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Check if venv exists
if (-not (Test-Path ".\.venv")) {
    Write-Host "Error: Virtual environment not found. Run: python -m venv .venv" -ForegroundColor Red
    exit 1
}

# Activate venv
Write-Host "Activating Python virtual environment..." -ForegroundColor Cyan
& ".\.venv\Scripts\Activate.ps1"

# Check for Redis
Write-Host ""
Write-Host "Checking Redis..." -ForegroundColor Cyan
try {
    $redisRunning = $null
    Get-Process redis-server -ErrorAction Stop | Out-Null
    Write-Host "✓ Redis is already running" -ForegroundColor Green
} catch {
    Write-Host "⚠ Redis is not running" -ForegroundColor Yellow
    Write-Host "  To start Redis:"
    Write-Host "  - Option 1: redis-server (if installed locally)"
    Write-Host "  - Option 2: docker run -d -p 6379:6379 redis:latest"
    Write-Host ""
}

# Function to open new terminal and run command
function Start-InNewTerminal {
    param(
        [string]$Title,
        [string]$Command
    )

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "powershell.exe"
    $processInfo.Arguments = "-NoExit -Command `"$Command`""
    $processInfo.UseShellExecute = $true
    $processInfo.CreateNoWindow = $false
    [System.Diagnostics.Process]::Start($processInfo) | Out-Null
    Write-Host "✓ Started: $Title" -ForegroundColor Green
}

# Start services in separate terminal windows
Write-Host ""
Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

# Backend
$backendCmd = "cd `"$scriptDir`" && .\.venv\Scripts\Activate.ps1 && flask --app backend --debug run --port=5000"
Start-InNewTerminal "Backend (http://localhost:5000)" $backendCmd

# Celery Worker
$celeryCmd = "cd `"$scriptDir`" && .\.venv\Scripts\Activate.ps1 && python -m celery -A backend.dota_bet_analyzer.celery worker --loglevel=info --pool=solo"
Start-InNewTerminal "Celery Worker" $celeryCmd

# Frontend
$frontendCmd = "cd `"$scriptDir\frontend`" && npm run dev"
Start-InNewTerminal "Frontend (http://localhost:5173)" $frontendCmd

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Services Started:" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "Backend:   http://localhost:5000" -ForegroundColor Cyan
Write-Host "Frontend:  http://localhost:5173" -ForegroundColor Cyan
Write-Host "Celery:    Running in background" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C in each terminal to stop services" -ForegroundColor Yellow
Write-Host ""
