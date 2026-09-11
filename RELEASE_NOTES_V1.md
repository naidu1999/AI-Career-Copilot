# Karna OS v1.0.0

- Dual deployment modes: login-free personal local and authenticated hosted.
- Supabase email/password signup, login, refresh, logout and server-side account deletion.
- Secure HttpOnly/SameSite cookies, HTTPS cookie enforcement and trusted-origin checks.
- Per-user isolation for profiles, resumes, evidence/history, sources, matches,
  applications/events, notifications, scan history and AI artifacts.
- Shared non-personal job catalogue with per-user matching.
- Hosted whole-database backups blocked; exports are user-scoped.
- Two-user automated isolation coverage in addition to parser, matcher, migration,
  connector, scheduler and application tests.
- SQLite WAL, busy timeout, indexes, pagination, single-transaction recalculation and
  concurrent source fetching.
- Docker/Compose, Render blueprint, preflight, CI, health check and deployment handoff.

Production deployment still requires the owner to configure Supabase and hosting
environment values. No secret is bundled in the release.
