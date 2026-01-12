#!/bin/bash
# Start development environment: Redis, Celery, Backend, and Frontend
# Usage: ./start-dev.sh

echo "Starting Dota Bet Analyzer Development Environment..."
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment not found. Run: python -m venv .venv"
    exit 1
fi

# Activate venv
echo "Activating Python virtual environment..."
source .venv/bin/activate

# Check for Redis
echo ""
echo "Checking Redis..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo "✓ Redis is already running"
    else
        echo "⚠ Redis is not running"
        echo "  Start with: redis-server"
    fi
else
    echo "⚠ Redis not found"
    echo "  Install: brew install redis (macOS) or apt install redis-server (Linux)"
    echo "  Or use Docker: docker run -d -p 6379:6379 redis:latest"
fi

# Start services
echo ""
echo "Starting services..."
echo ""

# Backend
echo "✓ Starting Backend (http://localhost:5000)"
flask --app backend --debug run --port=5000 &
BACKEND_PID=$!

# Celery Worker
echo "✓ Starting Celery Worker"
python -m celery -A backend.dota_bet_analyzer.celery worker --loglevel=info --pool=solo &
CELERY_PID=$!

# Frontend
echo "✓ Starting Frontend (http://localhost:5173)"
cd frontend
npm run dev &
FRONTEND_PID=$!

cd "$SCRIPT_DIR"

echo ""
echo "========================================"
echo "Services Started:"
echo "========================================"
echo "Backend:   http://localhost:5000"
echo "Frontend:  http://localhost:5173"
echo "Celery:    Running in background"
echo ""
echo "PIDs: Backend=$BACKEND_PID, Celery=$CELERY_PID, Frontend=$FRONTEND_PID"
echo ""
echo "To stop all services, run: kill $BACKEND_PID $CELERY_PID $FRONTEND_PID"
echo ""

# Wait for all processes
wait
