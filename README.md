# dota.Bet.Analyzer

The web application provides analytic services and highlights about the Dota 2 teams on the pro scene to help make better-informed bets. This README covers getting started with development, testing, database initialization, and running the backend.

**This project was created for coding learning purpose**

---

## Reference docs

- [Design document](https://docs.google.com/document/d/1cZAYBXYHw53i2RaiGt1aULUnfeAEof5mljG1PHHO99Q/edit?usp=sharing)

---

## 🚀 Quick Start

Get the project running **from scratch**. Choose your platform:

### Windows (PowerShell)

```powershell
# 1. Install prerequisites (if not already installed)
# - Python 3.14: https://www.python.org/downloads/
# - Node.js LTS: https://nodejs.org/
# - Docker Desktop: https://www.docker.com/products/docker-desktop/

# 2. Clone and navigate
git clone <repository-url>
cd dota.Bet.Analyzer

# 3. Set execution policy (once per machine)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 4. Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 5. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
npm install

# 6. Start Redis (in a new terminal)
docker run -d --name redis-dota -p 6379:6379 redis:latest

# 7. Run all services ⭐
npm run dev
```

✅ Open browser to **http://localhost:5173**
- Backend: http://localhost:5000
- Frontend: http://localhost:5173

---

### Linux (Bash)

```bash
# 1. Install prerequisites
# Linux: sudo apt install python3.14 nodejs docker.io

# 2. Clone and navigate
git clone <repository-url>
cd dota.Bet.Analyzer

# 3. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
npm install

# 5. Start Redis (in a new terminal)
docker run -d --name redis-dota -p 6379:6379 redis:latest

# 6. Run all services ⭐
npm run dev
```

✅ Open browser to **http://localhost:5173**
- Backend: http://localhost:5000
- Frontend: http://localhost:5173

---

### ✅ Verification Checklist

After running the commands above:

- [ ] **Backend** at http://localhost:5000 shows OpenAPI spec
- [ ] **Frontend** at http://localhost:5173 displays the UI
- [ ] **Terminal log shows** "ready to accept tasks" (Celery worker)
- [ ] **No connection errors** for Redis
- [ ] **Try it** → Enter two team names and click "Compare Teams"

**❌ Something not working?** Jump to **[🆘 Troubleshooting](#-troubleshooting)** →

---

### 📖 Next Steps (After Quick Start)

1. **Explore the UI** - Try searching for teams like "Liquid" or "Alliance"
2. **Check the API** - Visit http://localhost:5000/api/swagger-ui to see all endpoints
3. **Run the tests** - `npm test` to ensure everything works
4. **Read the code** - Start with [backend/dota_bet_analyzer.py](backend/dota_bet_analyzer.py) and [frontend/src/App.tsx](frontend/src/App.tsx)
5. **Check git workflow** - See **[VERSIONING.md](VERSIONING.md)** for development practices

---

### 🎯 Common Commands (Quick Reference)

Once your environment is set up, these are the commands you'll use most:

| Task | Command |
|------|---------|
| **Start everything** | `npm run dev` |
| **Run tests** | `npm test` |
| **Start backend only** | `npm run backend` |
| **Start frontend only** | `npm run frontend` |
| **Activate Python venv** | `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (Linux) |
| **Initialize databases** | `flask --app backend init-db` then `python scripts/init_d2ba_db.py` |
| **View API docs** | Open http://localhost:5000/api/swagger-ui |
| **Stop Redis** | `docker stop redis-dota && docker rm redis-dota` |

---

## 📚 Table of Contents

- **🚀 [Quick Start](#-quick-start)** ← Start here!
- **[Project Structure](#-project-structure-first-look)** - Understand the codebase layout
- **[Common Commands](#-common-commands-quick-reference)** - Frequently used commands
- **[Prerequisites](#-prerequisites)** - What you need to install
- **[Setup](#-setup-venv--dependencies)** - Detailed setup instructions
- **[Docker & Redis](#-docker--redis-setup-required-for-celery)** - Message broker setup
- **[Running Services](#-starting-all-services-recommended)** - How to start the app
- **[Testing](#-running-tests)** - Running the test suite
- **[Backend](#-backend-flask--python)** - Backend documentation
- **[Frontend](#-frontend-react--vite--typescript)** - Frontend documentation
- **[Getting Help](#-getting-help)** - Where to find answers
- **[Troubleshooting](#-troubleshooting)** - Fix common issues
- **[Tips & Notes](#-notes--tips)** - Useful knowledge

---

## 📂 Project Structure (First Look)

```
dota.Bet.Analyzer/
├── backend/                 # Flask API + Celery tasks
│   ├── dota_bet_analyzer.py # Main app & routes
│   ├── stats.py            # Statistics logic
│   ├── pro_players.py      # Pro player management
│   └── db.py               # Database initialization
├── frontend/               # React + Vite + TypeScript UI
│   ├── src/
│   │   ├── App.tsx         # Main component
│   │   └── components/     # React components
│   └── vite.config.ts      # Build configuration
├── scripts/                # Utility scripts
│   ├── generate_schema.py  # Generate DB schema
│   └── init_d2ba_db.py     # Initialize pro players DB
├── tests/                  # Test suite
│   ├── test_*.py           # Backend tests
│   └── conftest.py         # Test configuration
├── instance/               # Runtime data (git ignored)
│   ├── opendota.sqlite     # Main database
│   └── d2ba.sqlite         # Pro players/teams database
├── package.json            # npm scripts & dependencies
├── requirements.txt        # Python dependencies
└── README.md              # You are here!
```

**Key files to explore:**
- **Backend entry**: [backend/dota_bet_analyzer.py](backend/dota_bet_analyzer.py)
- **Frontend entry**: [frontend/src/App.tsx](frontend/src/App.tsx)
- **Tests config**: [tests/conftest.py](tests/conftest.py)

---

## ✅ Prerequisites

> **New to the project?** Jump to **[🚀 Quick Start](#-quick-start)** instead - it covers everything below!

### Required

1. **Python 3.14** (or 3.11+)
   - Download: https://www.python.org/downloads/
   - Verify: `python --version`

2. **Node.js LTS**
   - Download: https://nodejs.org/
   - Verify: `npm --version` and `node --version`

3. **Docker Desktop** (for Redis)
   - Download: https://www.docker.com/products/docker-desktop/
   - Verify: `docker --version`
   - Alternative: Install Redis locally (https://redis.io/download)

4. **Git**
   - Download: https://git-scm.com/download
   - Verify: `git --version`

### Optional

5. **Visual Studio Code** (recommended for development)
   - Download: https://code.visualstudio.com/
   - Install extensions listed in **[🛠️ Recommended VS Code Extensions](#-recommended-vs-code-extensions)** section

---

## 🛠️ Recommended VS Code Extensions

- **GitLens — Git supercharged** (eamodio.gitlens) - Better Git visualization
- **GitHub Copilot** (GitHub.copilot) - AI code assistant
- **Python** (ms-python.python) - Python support and debugging
- **JSON Tools** (eriklynd.json-tools) - JSON formatting
- **SQLite** (alexcvzz.vscode-sqlite) - View and edit SQLite databases

> Tip: Open VS Code Extensions Marketplace (`Ctrl+Shift+X`) and search for extension names or IDs

---

## � Setup (venv & dependencies)

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

Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Key Dependencies:**
- Flask 2.0+ - Web framework
- flask-smorest 0.40+ - OpenAPI/Swagger documentation
- marshmallow 3.20+ - Schema validation and serialization
- Celery 5.2+ - Async task processing
- Redis 4.0+ - Message broker and cache

---

## 🐳 Docker & Redis Setup (Required for Celery)

### Quick Start (Docker)

**Windows:**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Start Docker Desktop

**Linux:**
1. Install Docker: `sudo apt install docker.io`
2. Start Docker: `sudo systemctl start docker`

**Run Redis (both platforms):**
```bash
docker run -d --name redis-dota -p 6379:6379 redis:latest
```

**Verify Redis is running:**
```bash
docker ps  # Should list the redis-dota container
```

## 🔧 VS Code Configuration

### Python Virtual Environment Setup

1. Open Command Palette: `Ctrl+Shift+P`
2. Search for "Python: Select Interpreter"
3. Choose `.\.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (Linux)

### Recommended VS Code Settings

Add to workspace `settings.json` (`.vscode/settings.json`):

```json
{
  "python.formatting.provider": "black",
  "python.linting.enabled": true,
  "python.linting.mypyEnabled": true,
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "ms-python.python",
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true
  },
  "[json]": {
    "editor.formatOnSave": true
  }
}
```

---

## 🧹 Code Quality & Pre-commit Hooks

Enable and run pre-commit hooks (once per machine):

```bash
pre-commit install
pre-commit run --all-files
```
The hooks enforce:
- **Black** - Python code formatting
- **isort** - Import sorting
- **Ruff** - Python linting
- **mypy** - Type checking

---

## 🧪 Running Tests

Run the full test suite:

**Using npm (recommended - cross-platform):**
```bash
npm test
```

This runs:
- Backend tests: `pytest tests/ -v`
- Frontend tests: `vitest`

**Using pytest directly (backend only):**
```bash
python -m pytest -q
```

Run a specific test file:
```bash
python -m pytest tests/test_schema_valid.py -v
```

Run a specific test function:
```bash
python -m pytest tests/test_schema_valid.py::test_function_name -v
```

**Using vitest (frontend only):**
```bash
cd frontend
npm test          # Watch mode
npm test -- --run # Single run
```

**Test Results:**
- Backend: `test-results/backend/junit.xml`
- Frontend: `test-results/frontend/junit.xml`

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

This creates `instance/d2ba.sqlite` with `pro_players` and `teams` tables for storing Dota 2 professional player and team data.

**Sync Pro Players Data:**

Once the backend is running, sync the pro players database:

```bash
curl -X POST http://localhost:5000/api/pro-players/sync
```

**Sync Teams Data:**

Sync teams data from OpenDota API (paginated, ~1000 teams per page):

```bash
curl -X POST http://localhost:5000/api/teams/sync
```

Or use your API client to send POST requests to:
- `http://localhost:5000/api/pro-players/sync` - Sync professional players
- `http://localhost:5000/api/teams/sync` - Sync all teams (handles pagination automatically)

See [backend/PRO_PLAYERS_README.md](backend/PRO_PLAYERS_README.md) for detailed documentation.

---

## 📡 API Documentation

The backend provides a **Swagger UI** for interactive API documentation and testing:

**🔗 Swagger UI:** http://localhost:5000/api/swagger-ui

The API uses:
- **flask-smorest** for OpenAPI 3.0.2 specification
- **marshmallow** for request/response validation
- **RFC 7807-inspired** error responses with structured format

**Quick Example:**
```bash
# Sync pro players
curl -X POST http://localhost:5000/api/pro-players/sync

# Search teams
curl "http://localhost:5000/api/teams/search?q=liquid&limit=5"
```

All endpoints, request schemas, response formats, and error codes are documented in Swagger UI

---

## ▶️ Starting All Services (Recommended)

### Prerequisites
- Python 3.14+ with venv activated
- Node.js and npm installed
- Redis running (Docker or locally)
- Dependencies installed: `pip install -r requirements.txt` and `npm install`

### Option 1: npm (Cross-platform) ⭐ Recommended

```bash
npm run dev
```

This starts all services in one terminal using `concurrently`:
- **Backend** (Flask) → http://localhost:5000
- **Frontend** (Vite + React) → http://localhost:5173
- **Celery Worker** → processes async tasks

**Note:** npm scripts automatically use the virtual environment's Python (via `scripts/run-with-venv.js`). No manual venv activation needed.

### Option 2: PowerShell (Windows Only)

```powershell
.\start-dev.ps1
```

This launches:
- **Backend** (Flask) → http://localhost:5000
- **Frontend** (Vite + React) → http://localhost:5173
- **Celery Worker** → processes async tasks
- Checks for **Redis** connection

### Option 3: Bash/Shell (Linux)

```bash
chmod +x start-dev.sh
./start-dev.sh
```

---

## ▶️ Starting Individual Services

### Backend (Flask)

```bash
# Using npm:
npm run backend

# Or direct Flask (requires manual venv activation):
flask --app backend --debug run
```

Backend runs at `http://localhost:5000`

### Frontend (Vite)

```bash
cd frontend
npm run dev
```

Frontend runs at `http://localhost:5173`

### Celery Worker (Async Task Processing)

```bash
# Using npm:
npm run celery

# Or direct celery command:
# Development (Windows-compatible solo pool):
python -m celery -A backend.dota_bet_analyzer.celery worker --loglevel=info --pool=solo

# Production (Unix-compatible process pool):
python -m celery -A backend.dota_bet_analyzer.celery worker --loglevel=info --pool=prefork
```

**Note:** Development uses `solo` pool for Windows compatibility. Windows does not support `prefork`.

### Redis (Message Broker & Cache)

Required for Celery task queue.

```bash
# Docker (recommended):
docker run -d -p 6379:6379 redis:latest

Redis is used for:
- Celery task queue (message broker)
- Progress tracking (SSE updates)
- Task result backend

---

## 🔧 Backend (Flask + Python)

The backend provides REST API endpoints for team statistics, match data, and player analytics.

**📖 API Documentation:** http://localhost:5000/api/swagger-ui (when server is running)

### Core Features

#### Team Statistics (`/statistics`)
- Compare Dota 2 teams side-by-side (1-10 teams)
- Returns team ratings, tags, IDs, and rating deltas
- Initiates async tasks to fetch player match statistics
- Supports GET requests with query parameters: `?team=Alpha&team=Beta` or `?team1=Alpha&team2=Beta`

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

### Test Data Isolation

**Best practices implemented:**

✅ **Separate Database Per Test** - Each test gets its own temporary database, preventing any cross-contamination with production data or other tests.

✅ **Automatic Cleanup** - Temporary files and directories are automatically cleaned up after each test using pytest fixtures.

✅ **Mocked External APIs** - External API calls to OpenDota are mocked to prevent network requests and ensure test determinism.

✅ **Database Performance Logging** - All insert/update operations log execution time and throughput (records/sec):
```
Stored/updated 32 pro players in 0.045s (711.1 records/sec)
Stored/updated 1523 teams in 0.234s (6505.1 records/sec)
```

**Test configuration** is centralized in `tests/conftest.py`:
- `app` fixture: Creates isolated Flask test app with temp database
- `client` fixture: Provides test client for making requests
- Automatic database initialization with schema
- Cleanup guaranteed even if tests fail

**Database files used:**
- **Production**: `instance/opendota.sqlite` (main DB), `instance/d2ba.sqlite` (pro players/teams)
- **Testing**: Temporary directories created per test, cleaned up automatically

This isolation ensures:
- Tests cannot affect production data
- Tests can run in parallel safely
- No flaky tests from shared state
- Easy debugging with complete test database copies

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

## 💬 Getting Help

### For New Users
1. **First time setup trouble?** → Go to **[🆘 Troubleshooting](#-troubleshooting)** section below
2. **Lost in the code?** → Check **[📂 Project Structure](#-project-structure)** to find files
3. **Don't know what to do next?** → See **[📖 Next Steps](#-next-steps-after-quick-start)** in Quick Start
4. **Need to debug?** → Add print statements or use VS Code debugger (see **[🔧 VS Code Configuration](#-vs-code-configuration)**)

### For Developers
- **Test failures?** See **[🧪 Running Tests](#-running-tests)** section
- **Database issues?** See **[🗂️ Database initialization](#-%EF%B8%8F-database-initialization)** section
- **API questions?** Visit http://localhost:5000/api/swagger-ui (Swagger UI) when backend is running
- **Code questions?** Check docstrings in source files or read [Design document](https://docs.google.com/document/d/1cZAYBXYHw53i2RaiGt1aULUnfeAEof5mljG1PHHO99Q/edit?usp=sharing)

### Quick Reference
| Problem | Solution |
|---------|----------|
| "Module not found" | Activate venv or use `npm` commands |
| "Redis connection error" | Start Redis: `docker run -d -p 6379:6379 redis:latest` |
| "Port already in use" | Change port or kill existing process |
| "Tests failing" | Clear cache: `rm -rf __pycache__ .pytest_cache` |
| "Stuck on loading" | Check browser console (F12) for errors |

---

## 🆘 Troubleshooting

### Python/venv Issues

**"ModuleNotFoundError: No module named flask/celery/redis"**
- Ensure venv is activated: `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (Unix)
- Or use `npm` commands which handle venv automatically
- Reinstall dependencies: `pip install -r requirements.txt`

**"Python 3.14 not found"**
- Download Python 3.14 from https://www.python.org/downloads/
- Or use Python 3.11+ as a temporary measure (adjust `pyproject.toml` if needed)

**PowerShell Execution Policy Error**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Redis Connection Issues

**"Error connecting to Redis"**
- Verify Redis is running: `docker ps` (Docker) or check for redis-server process
- Start Redis: `docker run -d --name redis-dota -p 6379:6379 redis:latest`
- Default Redis port is 6379

### Test Issues

**"Tests failing locally but passing in CI"**
- Clear Python cache: `rm -rf __pycache__ .pytest_cache` (Unix) or `Remove-Item -Recurse __pycache__, .pytest_cache` (PowerShell)
- Reinstall dependencies: `pip install -r requirements.txt`
- Check for leftover temp files in `tests/` directory

**"vitest not found"**
- Ensure frontend dependencies installed: `cd frontend && npm install`
- Reinstall: `npm install` in workspace root

---

## 💡 Notes & Tips

### Database Configuration
- `app.config['DATABASE_FILENAME']` controls the DB filename (defaults to `opendota.sqlite`)
- Full path used is `app.instance_path / DATABASE_FILENAME`
- Pro players stored in separate `d2ba.sqlite` database

### Schema Management
- The repository contains tests that verify schema correctness
- Prefer updating `backend/schema.txt` and running `scripts/generate_schema.py` rather than editing `opendota_schema.sql` manually
- Verify schema: `python scripts/generate_schema.py --check`
- Add CI checks to ensure schema is up to date on push
