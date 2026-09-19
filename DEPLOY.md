# Deploying Karna OS

Two supported paths. Both use the same image/config — they differ in who has accounts.

---

## Path A — Personal / single-machine (what you run today)

No auth, no keys, SQLite local. Perfect for one person (or shared PC with local profiles).

### Run with Docker

```powershell
docker compose up -d --build
```

- App on http://localhost:8000 · data persists in the `karna_data` volume
- Logs: `docker compose logs -f` · Stop: `docker compose down`

### Run without Docker (current setup)

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

> **Windows note:** the Docker path needs **WSL2** (`wsl --install` in an admin PowerShell, then reboot). Docker Desktop cannot start its engine without it.

---

## Path B — Hosted multi-user (public/team deployment)

### 1. Prerequisites

- A Linux host or VPS (Ubuntu 22.04+ recommended) — or WSL2-enabled Windows
- Docker + Compose installed
- A **Supabase** project (free tier is fine) — this is the identity provider

### 2. Supabase checklist

1. Create a project at supabase.com
2. **Authentication → Providers → Email**: enable; turn *Confirm email* on or off to taste
3. **Authentication → URL Configuration**: set *Site URL* to your public URL (e.g. `https://karna.example.com`) and add it to *Redirect URLs*
4. Copy from **Project Settings → API**:
   - `Project URL` → `SUPABASE_URL`
   - `anon public` key → `SUPABASE_PUBLISHABLE_KEY`
   - `service_role` key → `SUPABASE_SECRET_KEY` *(secret — never expose)*

### 3. Environment (`.env` on the server)

```ini
DEPLOYMENT_MODE=hosted
TRUST_PROXY_HEADERS=true
SESSION_COOKIE_SECURE=true
PUBLIC_BASE_URL=https://karna.example.com
SUPABASE_URL=https://<proj>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<anon key>
SUPABASE_SECRET_KEY=<service_role key>
# AI (optional — keyless Pollinations fallback works with nothing)
GROQ_API_KEY=
```

### 4. HTTPS (required — cookies are `Secure`)

Easiest: Caddy in front, automatic certificates:

```
karna.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

(Alternatives: Nginx + certbot, or a Cloudflare Tunnel — no open ports needed.)

### 5. Launch

```powershell
docker compose up -d --build
curl https://karna.example.com/api/health   # expect {"status":"healthy"}
```

Sign-up is now open at `/app` → each user gets an isolated workspace (own resume, evidence, sources, matches, tracker).

---

## Production checklist

| Item | Value / check |
|---|---|
| `DEPLOYMENT_MODE=hosted` | set for Path B |
| `TRUST_PROXY_HEADERS=true` | set when behind Caddy/Nginx/Cloudflare |
| HTTPS active | login will not work without it (`Secure` cookies) |
| Backups | automatic: nightly + **startup catch-up** if server was off at scan hour |
| Scale | SQLite is fine for a team; for high concurrency set `SECONDARY_DATABASE_URL` to Postgres |
| Updates | `git pull && docker compose up -d --build` (data volume survives rebuilds) |
| Tests before deploy | `pytest -q` → expect all green |
