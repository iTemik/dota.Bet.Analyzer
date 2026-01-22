# dota.Bet.Analyzer

The web application provides analytic services and highlights about the Dota 2 teams on the pro scene to help make better-informed bets. This README covers getting started with development, testing, database initialization, and running the backend.

---

## Reference docs

- [Design document](https://docs.google.com/document/d/1cZAYBXYHw53i2RaiGt1aULUnfeAEof5mljG1PHHO99Q/edit?usp=sharing)

---

## ✅ Prerequisites

1. Install Git
   - Windows: Install Git for Windows (https://git-scm.com/download/win) and use PowerShell or Git Bash.
   - macOS / Linux: Install via package manager (e.g., `brew install git` or `sudo apt install git`).

2. Install Python (3.14 recommended)
   - Download from https://www.python.org/downloads/ or use your package manager.
   - Verify: `python --version` (or `python3 --version`).

3. Install Node.js and npm
   - Download from https://nodejs.org/ (LTS version recommended).
   - Verify: `npm --version` and `node --version`.

4. Install Docker (for running Redis)
   - **Windows/macOS:** Download [Docker Desktop](https://www.docker.com/products/docker-desktop/)
     - After install, restart your computer
     - Verify: `docker --version` in terminal
   - **Linux:** `sudo apt install docker.io` and enable with `sudo systemctl start docker`
   - **Alternative (no Docker):** Install Redis locally from https://redis.io/download

5. Install Visual Studio Code (optional but recommended)
   - Download from https://code.visualstudio.com/

---

## 🛠️ Recommended VS Code Extensions

- **GitLens — Git supercharged** (eamodio.gitlens) ✅
- **GitHub Copilot** (GitHub.copilot) ✅
- **Python** (ms-python.python) ✅
- **JSON Tools** (eriklynd.json-tools) or any **JSON formatter** ✅
- **SQLite** (alexcvzz.vscode-sqlite) — view and edit SQLite DBs ✅


Tip: install the extensions above from the Extensions Marketplace in VS Code.

---

## 🐳 Docker & Redis Setup

### Quick Start (Docker)

**Windows/macOS:**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Start Docker Desktop (or `sudo systemctl start docker` on Linux)
3. Run Redis:
```bash
docker run -d --name redis-dota -p 6379:6379 redis:latest
```

**Verify Redis is running:**
```bash
docker ps  # Should list the redis-dota container
```

**Stop Redis:**
```bash
docker stop redis-dota
docker rm redis-dota
```

### Alternative: Install Redis Locally

**Windows (via Chocolatey):**
```powershell
choco install redis
redis-server
```

**macOS:**
```bash
brew install redis
redis-server
```

**Linux:**
```bash
sudo apt install redis-server
redis-server
```

---

Enable and run pre-commit hooks (once per machine):

```bash
pre-commit install
pre-commit run --all-files
```

Update hooked repositories to latest pinned revisions:

```bash
pre-commit autoupdate
```

Recommended VS Code settings (add to workspace `settings.json`):

```json
{
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.linting.enabled": true,
  "python.linting.mypyEnabled": true
}
```

---

## 📦 Setup (venv & dependencies)

> **TODO:** add info how to configure venv in VS Code

### Windows PowerShell - Initial Setup

If you encounter a PowerShell execution policy error when running commands, run this once per machine:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

This allows locally created scripts to run while maintaining security. You'll need to confirm the policy change when prompted.

### Setup Instructions

From the project root:

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
---

## 🧪 Running Tests

Run the full test suite:

**Using npm (recommended - cross-platform):**
```bash
npm test
```

This runs:
- Backend tests: `pytest`
- Frontend tests: `vitest`

**Using pytest directly (backend only):**
```bash
python -m pytest -q
```

If you only want a single test file:
```bash
python -m pytest tests/test_schema_valid.py -q
```

**Using vitest (frontend only):**
```bash
cd frontend && npm test -- --run
```

---

## 🗂️ Database initialization

This project uses SQLite for local development with **two separate databases**:

1. **opendota.sqlite** - Main OpenDota schema database
2. **d2ba.sqlite** - Statistics database

### Main Database (opendota.sqlite)

The DB schema is generated from `backend/schema.txt` (which is opendota response for [api/schema](https://api.opendota.com/api/schema)) into `backend/opendota_schema.sql` by the script `scripts/generate_schema.py`.

- Regenerate schema:

```bash
python scripts/generate_schema.py
```

- Verify generated schema matches committed file:

```bash
python scripts/generate_schema.py --check
```

- Initialize the database (create tables):

Set the Flask app to use the application factory and run the CLI command:

```
flask --app backend init-db
```

### Pro Players Database (d2ba.sqlite)

Initialize the pro players database:

```bash
python scripts/init_d2ba_db.py
```

This creates `instance/d2ba.sqlite` with a `pro_players` table for storing Dota 2 professional player data.

**Fetch Pro Players Data:**

Once the backend is running, sync the pro players database:

```bash
curl -X POST http://localhost:5000/api/pro-players/sync
```

Or use your API client to send a POST request to http://localhost:5000/api/pro-players/sync

See [backend/PRO_PLAYERS_README.md](backend/PRO_PLAYERS_README.md) for detailed documentation.

---

## ▶️ Starting All Services (One Click)

### Option 1: PowerShell (Windows)

```powershell
.\start-dev.ps1
```

This launches:
- **Backend** (Flask) → http://localhost:5000
- **Frontend** (Vite + React) → http://localhost:5173
- **Celery Worker** (for async tasks)
- Checks for **Redis** connection

### Option 2: npm/Node.js (Cross-platform) ⭐ Recommended

Install frontend dependencies first:
```bash
npm install
```

**Windows PowerShell - First Time Setup:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**macOS/Linux - First Time Setup:**
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Then run all services:
```bash
npm run dev
```

> **Note:** npm scripts automatically use the virtual environment's Python (via `scripts/run-with-venv.js`). No manual venv activation needed for npm commands.

This uses `concurrently` to start all services in the same terminal:
- Backend (Flask) → http://localhost:5000
- Frontend (Vite) → http://localhost:5173
- Celery Worker → processing async tasks

### Option 3: Bash/Shell (macOS/Linux)

```bash
chmod +x start-dev.sh
./start-dev.sh
```

---

## ▶️ Starting Individual Services

**Backend only (Flask):**
```bash
# Using npm:
npm run backend

# Or direct Flask:
flask --app backend --debug run
```

**Frontend only (Vite):**
```bash
cd frontend && npm run dev
```

**Celery Worker:**
```bash
# Using npm:
npm run celery

# Or direct celery command:
# Development (uses solo pool for Windows compatibility):
python -m celery -A backend.dota_bet_analyzer.celery worker --loglevel=info --pool=solo

# Production (uses process pool):
python -m celery -A backend.dota_bet_analyzer.celery worker --loglevel=info --pool=prefork
```

**Redis** (required for Celery message broker):
```bash
# Using Docker (recommended):
docker run -d -p 6379:6379 redis:latest

# Or if installed locally:
redis-server
```

The app uses Redis for:
- Celery task queue (message broker)
- Progress tracking (SSE updates)
- Task result backend

---

## 🔧 Backend (Flask + Python)

The backend provides REST API endpoints for team statistics, match data, and player analytics.

### Core Features

#### Team Statistics (`/statistics`)
- Compare two Dota 2 teams side-by-side
- Returns team ratings, tags, IDs, and rating deltas
- Processes match history data and calculates aggregate statistics
- Supports both GET and POST requests with team names

#### Player Statistics Task (`/statistics/players`)
Async task for comprehensive player analysis:
- **Match Fetching**: Retrieves match history for multiple players (up to 10)
- **Player Rankings**: Fetches leaderboard rank for each player from OpenDota API
- **Rank Analysis**:
  - Calculates average player rank across the team
  - Tracks players "Tysyachniki"  with not so high rank (>1000) who may negatively impact team performance
- **Match Statistics**: Computes aggregate stats including:
  - Win percentage across rating matches
  - Tournament vs rating vs other match counts
  - Average matches per player
- **Progress Tracking**: Real-time progress updates via Redis and SSE streaming
- **Async Processing**: Uses Celery with Redis broker for background processing

**Task Workflow:**
1. Client calls `/statistics/players?account_id=123&account_id=456`
2. Backend starts Celery task and returns task_id
3. Frontend polls `/stream-progress/<task_id>` for real-time updates
4. Task processes matches, fetches ranks, calculates statistics
5. Results stored in Redis at `/results/<task_id>` when complete

#### Pro Players Database (`/ProPlayers`)
- Fetches professional Dota 2 players from OpenDota API
- Stores player data in SQLite database for reference
- Updates player information on demand

### Backend Testing

Comprehensive test suite with 76+ tests covering:
- Team statistics calculation
- Player rank fetching from OpenDota API
- Match summary computation (win percentage, average rank, bad rank players)
- API endpoint validation
- Error handling and edge cases

Run backend tests:
```bash
python -m pytest -q
```

---

## 🎨 Frontend (React + Vite + TypeScript)

The frontend is a modern React application for displaying team statistics and comparisons.

### Quick Start

From the `frontend` directory:

```bash
npm install       # Install dependencies
npm run dev       # Start development server (http://localhost:5173)
npm run build     # Build for production
npm test          # Run tests
```

### Features

#### Team Comparison Form
- Input two team names for comparison
- Form validation (both teams required)
- Keyboard support (Enter to submit)
- Auto-focus on first input field

#### Statistics Display
- **Team Metadata**: Tags, IDs, current ratings
- **Rating Delta**: Last match rating change with color coding
- **Match Analysis**:
  - Win percentage across all matches
  - Rating matches count
  - Tournament matches count
  - Other matches count
  - Average matches per player
- **Team Quality Metrics**:
  - Average player rank (lower is better - inverted color logic)
  - Bad rank players count (players with rank >1000, lower is better)

#### Color Highlighting
- **Green (Positive)**: Better performance (higher rating, higher win %, lower rank)
- **Red (Negative)**: Worse performance (lower rating, lower win %, higher rank)
- **Gray (Neutral)**: No difference or not applicable
- **Inverse Logic**: Rank and bad player count use inverse colors (lower = positive)

#### Real-time Polling
- Automatically polls for task completion every 5 seconds
- Displays progress updates to user
- Fetches summary statistics once task completes
- Handles task cancellation when new search starts
- Timeout protection (5-minute maximum)

#### Responsive Design
- Works on desktop and mobile devices
- Flexible table layout
- Clean, readable statistics display

### Development

The development server includes a proxy for API requests:
- `/statistics` requests are automatically forwarded to `http://localhost:5000` (Flask backend)

### Testing

Comprehensive test suite with 26 tests covering:
- Component rendering and structure
- Input validation (empty teams, whitespace handling)
- API integration and error handling (HTTP errors, network failures)
- Results display and data formatting
- Summary statistics display (win percentage, player ranks, bad players)
- Keyboard interaction (Enter to submit)
- Color coding logic (positive/negative/inverse)
- Polling behavior (progress updates, cancellation, timeout)

Run frontend tests:
```bash
npm test          # Watch mode
npm test -- --run # Single run
cd frontend && npm test -- --run  # From subdirectory
```

Test categories:
- **Rendering**: 4 tests (DOM structure, autofocus)
- **Input Validation**: 4 tests (empty fields, whitespace)
- **API Integration**: 4 tests (fetch calls, loading states, error handling)
- **Results Display**: 4 tests (statistics rendering, data formatting)
- **Summary Display**: 2 tests (summary statistics, rating matches)
- **Keyboard Input**: 2 tests (Enter key in form fields)
- **Delta Display**: 1 test (decimal formatting)
- **Color Highlighting**: 1 test (color logic for ratings)
- **Team Quality Metrics**: 2 tests (avg rank, bad players display)
- **Polling Management**: 2 tests (results clearing, polling cancellation)

For more details, see [frontend/README.md](frontend/README.md) and [frontend/TEST_GUIDE.md](frontend/TEST_GUIDE.md)

---

## 💡 Notes & Tips

- `app.config['DATABASE_FILENAME']` controls the DB filename (defaults to `opendota.sqlite`). The full path used is `app.instance_path / DATABASE_FILENAME`.
- The repository contains tests that verify schema correctness and a script to regenerate schema; prefer updating `schema.txt` and running the script rather than editing `opendota_schema.sql` manually.
- Add CI checks to ensure `scripts/generate_schema.py --check` runs on push (CI can fail when auto-generated files are out of date).
