# Windows 11 one-page setup

1. Install Python 3.12 x64. During setup, enable **Add Python to PATH**.
2. Confirm `py -0p` lists Python 3.12.
3. Extract Karna OS to a normal folder such as `C:\KarnaOS`; avoid OneDrive if possible.
4. Double-click `run_windows.bat`. The script creates a Python 3.12 virtual environment,
   installs pinned dependencies and starts the server.
5. Open `http://127.0.0.1:8000`. Keep the terminal open.
6. Stop with Ctrl+C. Start again with `run_windows.bat`.

Optional keys belong only in `.env`. The local matcher, database, evidence review,
application tracking and backups work without cloud keys.

If setup fails, delete only the project’s `.venv` folder and run the script again.
Never delete the `data` folder unless you intentionally want to remove local records.
