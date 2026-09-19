@echo off
setlocal
title Karna OS
cd /d "%~dp0"

rem ---------------------------------------------------------------
rem  Karna OS one-click launcher for Windows
rem  First run: installs everything (needs Python, ~2-3 minutes).
rem  Every run after: starts the app and opens your browser.
rem ---------------------------------------------------------------

if not defined KARNA_PORT set KARNA_PORT=8000

rem Fast path: an existing virtual environment is already version-pinned.
if exist ".venv\Scripts\python.exe" goto :have_venv

set "PYCMD="

rem Prefer an exact usable version via the py launcher (most common setup).
py -3.12 --version >nul 2>nul && set "PYCMD=py -3.12"
if defined PYCMD goto :have_pycmd
py -3.13 --version >nul 2>nul && set "PYCMD=py -3.13"
if defined PYCMD goto :have_pycmd
py -3.11 --version >nul 2>nul && set "PYCMD=py -3.11"
if defined PYCMD goto :have_pycmd

rem Fall back to plain python, unless it is 3.14 (not yet supported by our
rem pinned libraries). Karna OS needs Python 3.11-3.13.
where python >nul 2>nul
if errorlevel 1 goto :no_python
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
if "%PYVER:~0,4%"=="3.14" goto :no_python
set "PYCMD=python"

:no_python
if not defined PYCMD (
  echo.
  echo   Karna OS needs Python 3.11, 3.12 or 3.13.
  echo.
  echo   The download page is opening. Install Python 3.12 and on the first
  echo   screen tick "Add python.exe to PATH", then double-click this again.
  echo.
  if not defined KARNA_NO_BROWSER start https://www.python.org/downloads/release/python-3128/
  pause
  exit /b 1
)

:have_pycmd
echo.
echo   First run: setting up Karna OS - one time only, 1-3 minutes...
echo.
%PYCMD% -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo   Setup failed - check your internet connection and try again.
  pause
  exit /b 1
)
echo   Setup complete.
echo.

:have_venv
if not exist ".env" copy ".env.example" ".env" >nul

set "PORT=%KARNA_PORT%"
set "LASTPORT="

rem This folder remembers its server's port, so two installs on one PC
rem never open each other's data.
if exist ".karna_port" set /p LASTPORT=<.karna_port
if not defined LASTPORT goto :check_free
curl -s --max-time 2 http://127.0.0.1:%LASTPORT%/ | findstr /I /C:"Karna" >nul 2>nul
if errorlevel 1 goto :check_free
set "PORT=%LASTPORT%"
goto :already

rem Preferred port occupied by some other program? Step aside.
:check_free
netstat -ano | findstr ":%PORT% " | findstr /C:"LISTENING" >nul 2>nul
if errorlevel 1 goto :start
set /a PORT=%PORT%+1
echo   Port %KARNA_PORT% is used by another program - trying port %PORT%...
goto :check_free

:start
echo   Starting Karna OS...
start "Karna OS server" /min ".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT%
timeout /t 5 /nobreak >nul

curl -s --max-time 3 http://127.0.0.1:%PORT%/api/health | findstr /C:"healthy" >nul 2>nul
if not errorlevel 1 goto :mark

echo   Still preparing (first start can take a moment)...
timeout /t 10 /nobreak >nul
curl -s --max-time 3 http://127.0.0.1:%PORT%/api/health | findstr /C:"healthy" >nul 2>nul
if not errorlevel 1 goto :mark

rem Self-heal: an interrupted first install leaves a broken venv. Finish it.
echo   Finishing setup (this happens if a previous run was interrupted)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
timeout /t 5 /nobreak >nul
curl -s --max-time 3 http://127.0.0.1:%PORT%/api/health | findstr /C:"healthy" >nul 2>nul
if not errorlevel 1 goto :mark

echo.
echo   Karna OS could not start. Easiest fix: delete the ".venv" folder in
echo   this window's folder, then double-click Start-Karna-OS.bat again.
echo.
pause
exit /b 1

:mark
(echo %PORT%)>.karna_port
goto :open

:already
echo   Karna OS is already running - opening it.

:open
if not defined KARNA_NO_BROWSER start "" http://127.0.0.1:%PORT%/

echo.
echo   Karna OS is running: http://127.0.0.1:%PORT%/
echo.
echo   - To stop it: close the minimized "Karna OS server" window.
echo   - Next time: just double-click this file again.
echo   - Your data stays in the "data" folder on this computer. Nothing
echo     is uploaded anywhere. Delete the folder to erase everything.
echo.
pause
