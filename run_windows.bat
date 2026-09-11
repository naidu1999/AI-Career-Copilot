@echo off
cd /d "%~dp0"
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Karna OS requires Python 3.12. Install it, then run this file again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
echo Open http://127.0.0.1:8000 in your browser.
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
