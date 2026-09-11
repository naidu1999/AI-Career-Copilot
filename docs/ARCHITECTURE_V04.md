# Karna OS v0.4 architecture

The browser talks only to the local FastAPI service. FastAPI stores profile, evidence,
jobs, matches, applications, events, notifications, scan history, and generated
artifacts in SQLite. Uploaded resumes remain in `data/uploads`.

Job connectors call documented JSON endpoints for Greenhouse, Lever, Ashby,
SmartRecruiters, Recruitee, Arbeitnow, Adzuna, Jooble, and optionally USAJOBS. Source
failures are isolated and reported; they do not abort the entire scan. Matching Engine
v3 runs locally after imports, scans, profile edits, and evidence edits.

The scheduler is an in-process daily task. Therefore the Windows server must be running
at the scheduled hour. This release is deliberately single-user and binds to
`127.0.0.1`. Secrets are server-side `.env` values and are never returned to the UI.

Application Studio uses the configured optional OpenAI-compatible endpoint through one
gateway. Prompts include verified evidence and explicitly prohibit fabricated claims.
Every output requires human review and Karna OS never submits it.
