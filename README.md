---
title: Karna OS
emoji: 🎯
colorFrom: blue
colorTo: pink
sdk: docker
app_port: 8000
pinned: false
---

# Karna OS v1.1 Continuity

Karna OS is a personal, local-first career operating system. It discovers permitted job
metadata, performs explainable deterministic matching, prepares evidence-grounded career
material and tracks applications. It never uploads a resume to job portals or submits an
application automatically.

## Windows 11 quick start (share this with friends)

1. Install Python from https://www.python.org/downloads/ — on the first screen
   **tick "Add python.exe to PATH"** (any 3.12+ works; the launcher checks).
2. Extract the ZIP anywhere (outside OneDrive when possible).
3. Double-click **`Start-Karna-OS.bat`**.
4. Your browser opens Karna OS automatically — `http://127.0.0.1:8000`.

The first run installs everything (1–3 minutes, one time). After that it starts
in seconds. Your data lives in the local `data` folder and never leaves the
machine — delete the extracted folder to erase everything. Do not use Python
3.14, commit `.env`, or place secrets in frontend files.

## v1.1 capabilities

- Public marketing landing site at `/` with interactive matching, Interview Studio and AI-router demos; the dashboard lives at `/app`.
- Matching Engine v4: strict job-family, title, seniority, experience, location,
  authorization, sponsorship and mandatory-skill checks.
- Canonical vacancy deduplication across official ATS and aggregator sources.
- Source health, freshness, duration, errors, cooldowns, duplicates and targeted retry.
- Medium professional motion with score rings, skeletons, progress and reduced-motion.
- Configurable task-specific AI routing with rate-limit handling, cooldowns, circuit
  breakers, authorized cloud providers and local Ollama fallback.
- Role-aware Senior Recruiter Mode.
- Resume Studio with approval, change comparison and DOCX/PDF export.
- Interview Studio with job-specific generation, STAR builder and checklist.
- Application notes, stages, deadlines, follow-ups, interview details, rejection reasons,
  offer details and immutable history.
- Complete JSON export, storage dashboard, verified backups and guarded restore.
- Durable cloud-mirror outbox: local SQLite stays authoritative in personal mode;
  Supabase PostgreSQL is primary and a compatible PostgreSQL service can be secondary.
- Hosted authentication, user isolation, RLS contract, HTTPS enforcement, rate limiting,
  security headers, file-signature validation and dependency auditing.

## Free AI setup (unlimited, no cost)

The recommended path needs **no API keys and has no usage limits**: run the model
on your own machine with [Ollama](https://ollama.com).

1. Install Ollama and run `ollama pull qwen2.5:7b` (or any model you prefer).
2. In `.env` set `AI_PROVIDER=ollama`.
3. Restart Karna OS — summaries, tailoring and coaching now run locally,
   offline and unlimited.

Free cloud fallbacks (optional, in router order):

- **Google Gemini** — free-tier key from [aistudio.google.com](https://aistudio.google.com),
  roughly a few hundred requests per day on flash models.
- **OpenRouter** — one key, 30+ free models at [openrouter.ai](https://openrouter.ai).

Paid providers stay disabled unless you explicitly allow them per task in the
**Continuity & Data → AI Continuity Router**.

## AI configuration

ChatGPT Plus does not provide OpenAI API quota. Use authorized API credentials or Ollama.
The default is free-first with paid providers disabled. Configure only providers you own:

```env
OLLAMA_MODEL=qwen2.5:7b
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
OPENAI_API_KEY=
OPENAI_MODEL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
GEMINI_API_KEY=
GEMINI_MODEL=
```

Change task order and paid permission in **Continuity & Data → AI Continuity Router**.

## Cloud mirror

Cloud mirroring is off by default. For continuity, supply standard PostgreSQL connection
strings and enable it:

```env
CLOUD_SYNC_ENABLED=true
SUPABASE_DATABASE_URL=postgresql://...
SECONDARY_DATABASE_URL=postgresql://...
```

Karna OS writes locally first. Failed cloud writes remain in a retry queue, and the
secondary is attempted only when the Supabase connection fails.

## Job sources

Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee and Arbeitnow need no key. Adzuna,
Jooble and USAJOBS require credentials in `.env`; USAJOBS remains disabled by default.
Only documented JSON endpoints are used.

## Validation

```powershell
python scripts/preflight.py
python -m pytest -q
```

## Distribution ZIP

Build a clean distributable archive (no secrets, virtual envs or local data;
`.env.example` is sanitized automatically):

```powershell
python scripts/make_zip.py
```

The archive is written to `dist/karna_os.zip`.

Read [Windows setup](docs/WINDOWS_SETUP.md), [architecture](docs/ARCHITECTURE_V11.md),
[AI routing](docs/AI_ROUTING.md), [backup and recovery](docs/BACKUP_RECOVERY.md),
[deployment](docs/DEPLOYMENT_HANDOFF.md), [troubleshooting](docs/TROUBLESHOOTING.md),
and [limitations](docs/LIMITATIONS.md).
