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

4. Install Visual Studio Code (optional but recommended)
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

## 🧰 Development tools & pre-commit

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

<em style="color:red">TODO: add info how to configure venv in VS Code</em>

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

<em style="color:red">TODO: add info how to configure launch.json and launch options for running tests in VS Code</em>

Run the test suite using pytest:

```
python -m pytest -q
```

If you only want a single test file:

```
python -m pytest tests/test_schema_valid.py -q
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

Once the backend is running, populate the database:

```bash
curl http://localhost:5000/ProPlayers
```

Or visit http://localhost:5000/ProPlayers in your browser.

See [backend/PRO_PLAYERS_README.md](backend/PRO_PLAYERS_README.md) for detailed documentation.

---

## ▶️ Starting the backend (development)

You can run the backend directly or use Flask CLI with the application factory.

Run directly (quick):

```
flask --app backend
```

The server will be available at http://127.0.0.1:5000 by default.

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

- **Team Statistics Form**: Compare two Dota 2 teams side-by-side
- **Real-time Results**: Display team ratings, tags, IDs, and deltas
- **Conditional Highlighting**: Color-coded backgrounds for performance indicators
- **Team Logos**: Displays team logos from backend data
- **Responsive Design**: Works on desktop and mobile

### Development

The development server includes a proxy for API requests:
- `/statistics` requests are automatically forwarded to `http://localhost:5000` (Flask backend)

### Testing

Comprehensive test suite with 21 tests covering:
- Component rendering
- Input validation
- API integration and error handling
- Results display logic
- Conditional styling

Run tests:
```bash
npm test          # Watch mode
npm test -- --run # Single run
```

For more details, see [frontend/README.md](frontend/README.md) and [frontend/TEST_GUIDE.md](frontend/TEST_GUIDE.md)

---

## 💡 Notes & Tips

- `app.config['DATABASE_FILENAME']` controls the DB filename (defaults to `opendota.sqlite`). The full path used is `app.instance_path / DATABASE_FILENAME`.
- The repository contains tests that verify schema correctness and a script to regenerate schema; prefer updating `schema.txt` and running the script rather than editing `opendota_schema.sql` manually.
- Add CI checks to ensure `scripts/generate_schema.py --check` runs on push (CI can fail when auto-generated files are out of date).
