# Upgrade an existing Karna OS folder to v0.4

1. Stop Uvicorn with `Ctrl+C`.
2. In the old version, create a backup from Overview and separately copy the complete
   `data` folder and `.env` file.
3. Extract v0.4 into a new folder; do not overwrite the old installation.
4. Copy the old `data/karna_os.db`, `data/uploads`, and `.env` into the new folder.
5. Delete the new folder's `.venv` if one exists, then run `run_windows.bat`.

Karna OS applies additive SQLite migrations on startup. If startup fails, keep the old
folder untouched and restore its copied `data` folder. API secrets are never included
in release ZIP files; retain your own `.env` securely.
