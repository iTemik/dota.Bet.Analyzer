# Quick Start Guide

## 🚀 One-Command Startup (Recommended)

### First Time Setup
1. Ensure Python 3.14+ and Node.js are installed
2. Clone the repository
3. Run once:
   ```bash
   npm install
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1  # Windows PowerShell
   # OR source .venv/bin/activate  # macOS/Linux
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Start Redis (Docker):
   ```bash
   docker run -d --name redis-dota -p 6379:6379 redis:latest
   ```

### Every Time You Work
```bash
npm run dev
```

This starts all three services in one terminal:
- **Backend** (Flask): http://localhost:5000
- **Frontend** (React): http://localhost:5173
- **Celery Worker**: processes async tasks

## 📊 Testing

```bash
npm test
```

Runs all tests:
- Backend: 56 tests ✅
- Frontend: 19 tests ✅

## 🔧 Individual Services

```bash
npm run backend      # Flask only
npm run celery       # Celery worker only
npm run frontend     # React dev server
npm run test:backend # Backend tests
npm run test:frontend # Frontend tests
```

## 🛠️ Troubleshooting

**"No module named celery/flask"?**
- Ensure venv is activated: `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (Unix)
- Or use npm commands which handle venv automatically

**Redis connection error?**
- Start Redis: `docker run -d --name redis-dota -p 6379:6379 redis:latest`
- Check it's running: `docker ps`

**Port already in use?**
- Flask (5000): Stop other Flask apps or change port in terminal
- Vite (5173): Uses next available port automatically
- Celery: Uses Redis internally, no port needed

## 📚 Full Documentation

See [README.md](README.md) for complete setup details, database initialization, and advanced topics.
