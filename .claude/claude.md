# Claude Rules - Dota Bet Analyzer

**Type hints required, docstrings for public functions, PEP 8 snake_case, PascalCase classes.**
**Run `python -m pre_commit run --all-files` after ANY Python change. Use PowerShell only (no bash).**
**Minimize changes in claude.md. Keep it efficient for claude code only**

## CRITICAL: Pre-Commit After Every Python Change
1. Verify venv: `.venv\Scripts\Activate.ps1` (check for `(.venv)` in prompt)
2. Run: `python -m pre_commit run --all-files`
3. Fix: `python -m black backend/` + `python -m isort backend/` + `python -m ruff check backend/ --fix`
4. Re-run until all pass

## Stack
- Backend: Python 3.14+ Flask + Celery (port 5000)
- Frontend: React 19.2.0 + TS 5.9.3 + Vite (port 5173)
- DB: SQLite + Redis (localhost:6379)
- Line length: 120 (Black/ESLint)

## Code Rules
- Type hints: All functions
- Docstrings: All public functions (Args, Returns)
- Error JSON: `{error_code: str, message: str, details: {url: str}}`
- REST prefix: `/api/`
- Python naming: snake_case functions, PascalCase classes
- TS naming: PascalCase components, camelCase functions

## Testing
- Run: `npm test`
- Test all public functions
- Test status codes: 200/201/400/404/500
- Reports: `test-results/*/junit.xml`
- Prod and tests db are separated

## PowerShell Only
NO bash commands. Use: `Get-Content` (cat), `Select-String` (grep), `Get-ChildItem` (ls), `Set-Location` (cd)

## Files
- Backend: [backend/dota_bet_analyzer.py](backend/dota_bet_analyzer.py), [backend/stats.py](backend/stats.py)
- Frontend: [frontend/src/App.tsx](frontend/src/App.tsx)
- Config: [pyproject.toml](pyproject.toml), [.pre-commit-config.yaml](.pre-commit-config.yaml)

## Commands
```powershell
.venv\Scripts\Activate.ps1              # Activate venv
python -m pre_commit run --all-files    # Pre-commit checks
python -m black backend/                # Format Python
python -m isort backend/                # Sort imports
python -m ruff check backend/ --fix     # Lint + fix
python -m pytest tests/ -q              # Run tests
npm run dev                             # Start Backend+Celery+Frontend (auto-checks Redis)
npm test                                # All tests
Get-Content backend/stats.py -Head 50   # View (PowerShell)
Select-String "pattern" backend/*.py    # Search
```

## Redis Setup (REQUIRED for `npm run dev`)
Redis must be running. **`npm run dev` will check automatically.**

Start Redis (choose one):
```powershell
# Option 1 - Docker (recommended)
docker run -d -p 6379:6379 redis:latest

# Option 2 - Local install: https://github.com/microsoftarchive/redis/releases
redis-server
```

Then run: `npm run dev` (will verify Redis is running first)

## Pre-Commit Checks
Black (format 120), isort (imports), Ruff (lint E,F,W,I,B,C,RUF), type hints, trailing whitespace, YAML/JSON validation

## Versions
Backend: `backend/VERSION`, Frontend: `frontend/src/version.ts`

## DB
Custom: [backend/d2ba_schema.sql](backend/d2ba_schema.sql), Session: [backend/db.py](backend/db.py)

## Error Handling
Always catch exceptions, return JSON `{error_code, message, details}` with proper HTTP status code

## Examples

**✅ Type hints (required):**
```python
def update_progress(task_id: str, step: int, progress: float) -> None:
    """Update progress in Redis."""
```

**❌ Missing type hints (fix this):**
```python
def update_progress(task_id, step, progress):
```

**✅ Minimize changes (only fix what's asked):**
```python
# Task: Add type hint to update_progress
# GOOD: Change only the function signature
def update_progress(task_id: str, step: int, progress: float) -> None:

# BAD: Refactor the whole function unnecessarily
def update_progress(task_id: str, step: int, progress: float) -> None:
    try:
        data = {"step": step}
        redis_client.setex(...)
    except Exception as e:
        logger.warning(str(e))
```

**✅ Docstring (required for public functions):**
```python
def get_version() -> tuple[Response, int]:
    """Get backend and frontend versions.

    Returns:
        Tuple of (JSON response, HTTP status code)
    """
```
