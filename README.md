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

3. Install Visual Studio Code (optional but recommended)
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

## 📦 Setup (venv & dependencies)

<em style="color:red">TODO: add info how to configure venv in VS Code</em>

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

This project uses SQLite for local development. The DB schema is generated from `backend/schema.txt` (which is opendota response for [api/schema](https://api.opendota.com/api/schema) ) into `backend/schema.sql` by the script `scripts/generate_schema.py`.

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

---

## ▶️ Starting the backend (development)

You can run the backend directly or use Flask CLI with the application factory.

Run directly (quick):

```
flask --app backend
```

The server will be available at http://127.0.0.1:5000 by default.

---

## 💡 Notes & Tips

- `app.config['DATABASE_FILENAME']` controls the DB filename (defaults to `dba.sqlite`). The full path used is `app.instance_path / DATABASE_FILENAME`.
- The repository contains tests that verify schema correctness and a script to regenerate schema; prefer updating `schema.txt` and running the script rather than editing `schema.sql` manually.
- Add CI checks to ensure `scripts/generate_schema.py --check` runs on push (CI can fail when auto-generated files are out of date).



