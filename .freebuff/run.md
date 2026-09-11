# Run doc — Karna OS (FastAPI + vanilla JS frontend)

## Reproduce artifacts (fresh checkout)

1. Install 64-bit Python 3.12 (`py -3.12 --version`).
2. Create the virtual env and install dependencies:
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. Environment file: copy `.env.example` to `.env` and adapt values
   (in the main checkout a working `.env` already exists; never commit or
   share it — it holds local credentials). No other build artifacts are
   required; the frontend is plain HTML/CSS/JS under `backend/static/`.
4. Optional sanity check: `.venv\Scripts\python.exe -m pytest -q`

## Run the server

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

- Default port: **8000** (from `.env` `PORT`); if busy, pass `--port 8123` etc.
- Landing site: `http://127.0.0.1:8000/` — dashboard: `http://127.0.0.1:8000/app`
- Detached start (PowerShell, distinct stdout/stderr files):
  ```powershell
  (Start-Process -FilePath '<abs>\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory '<abs>' -RedirectStandardOutput '<log>' -RedirectStandardError '<log>.err' -WindowStyle Hidden -PassThru).Id
  ```
- Stop: `taskkill /PID <pid> /F`
