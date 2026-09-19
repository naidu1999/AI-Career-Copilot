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

## Path C — Hugging Face Spaces (free hosting)

Runs the same Docker image on Hugging Face's free tier: `https://<your-name>-karna-os.hf.space`, HTTPS included, no card required.

### How it stays free (and keeps your data)

Free Spaces have an **ephemeral disk** and sleep after ~48h of inactivity. Karna OS handles this with **cloud snapshots**: on boot it restores the newest database snapshot, while running it uploads one every 20 minutes, and on shutdown it saves a final copy — all into a **private Supabase Storage bucket** (free tier). One honest caveat: the *parsed contents* of your resume live in the database and survive; the original uploaded PDF lives on the ephemeral disk, so re-upload the PDF after a cold restart.

### Steps

1. **Create the Space** — huggingface.co → New Space → name it `karna-os` → SDK: **Docker** → Public (or Private on the free tier) → Create.
2. **Push the code** — upload/push the repo (Dockerfile, `backend/`, `requirements.txt`, `README.md` with the `sdk: docker` frontmatter). Do **not** upload `.env` or `data/`.
3. **Add secrets** — Space → Settings → *Variables and secrets*:
   | Secret | Value |
   |---|---|
   | `SUPABASE_URL` | your Supabase project URL |
   | `SUPABASE_SECRET_KEY` | service_role key |
   | `SNAPSHOT_ENABLED` | `true` |
   | `SNAPSHOT_BUCKET` | `karna-snapshots` |
   | `SCAN_ENABLED` | `false` (recommended — scans need live outbound time) |
4. The Space builds (~5 min) and serves at `https://<name>-karna-os.hf.space`.
5. **Supabase side**: nothing to pre-create — the app makes the storage bucket on first upload.

### Multi-user on the Space

- **Just you:** leave `DEPLOYMENT_MODE=local` — your workspace restores from snapshots.
- **Team/public:** set `DEPLOYMENT_MODE=hosted` and complete the Supabase auth checklist from Path B (same keys, one project). Every visitor signs up and gets an isolated workspace.

### Free-tier limits (honest numbers)

- 2 vCPU / 16 GB RAM, no GPU — plenty for this app
- Sleeps after ~48h idle; wakes on the next visit (first load after sleep takes ~1 min while the snapshot restores)
- Snapshot size: the database gzips to a few MB — far under Supabase's free 1 GB

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
