# Upgrade from Karna OS v0.2

1. Stop the old server with `Ctrl+C`.
2. Make a copy of the entire old Karna OS folder.
3. Extract v0.3 into a new folder.
4. Copy the old `data/karna_os.db` into the new v0.3 `data` folder.
5. Copy the old `data/uploads` contents into the new v0.3 `data/uploads` folder.
6. Run `run_windows.bat` in v0.3. Database changes are applied automatically.

Do not copy `.venv`. Karna OS will create a fresh Python 3.12 environment. Keep
`.env` private; copy its values manually if you previously configured an AI provider.
