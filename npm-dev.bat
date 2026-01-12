@echo off
REM Activate venv and run npm dev
REM Usage: npm-dev.bat

call .\.venv\Scripts\activate.bat
npm run dev
