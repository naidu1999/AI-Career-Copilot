# Karna OS deployment handoff

## What is ready

- Python 3.12 Docker image, health check, non-root runtime and persistent data volume.
- Docker Compose for private/local server deployment.
- Render blueprint as a starting point; automatic deployment is disabled.
- CI workflow for preflight, compilation, tests and container build.
- Supabase v1.1 tables, indexes, private resume bucket and per-user RLS policies.
- Protected external scheduler endpoint using `X-Cron-Secret`.

## Hosted mode

Set `DEPLOYMENT_MODE=hosted`. The API then uses Supabase email/password authentication,
secure HttpOnly access/refresh cookies, origin checking, and per-user scoping for every
personal SQLite record. Jobs are intentionally shared; profiles, resumes, evidence,
sources, matches, applications, notifications, scans and generated artifacts are not.
Run hosted mode with exactly one API worker and persistent storage.

## Account-side work the owner must perform

1. Create a private GitHub repository and upload this project without `.env` or `data`.
2. Create a clean Supabase production project; run migrations 001, 002, 003 and 004 in order.
3. Enable email/password authentication and configure approved redirect URLs.
4. Create a hosting service from the Dockerfile and attach persistent storage.
5. Enter environment variables in the hosting dashboard—never in source control.
6. Generate a long random `CRON_SECRET`; configure the scheduler to POST to
   `/api/system/scheduled-scan` with header `X-Cron-Secret`.
7. Set `DEPLOYMENT_MODE=hosted` and the exact public HTTPS URL, run
   `python scripts/preflight.py`, then verify `/api/health`.
8. Configure monitoring against `/api/health`, test a staging restore and keep an
   encrypted backup outside the hosting provider.
9. Publish reviewed privacy/terms documents and obtain consent before accepting users.

## Required production environment variables

`APP_ENV`, `DEPLOYMENT_MODE`, `PUBLIC_BASE_URL`, `CRON_SECRET`, `SUPABASE_URL`,
`SUPABASE_PUBLISHABLE_KEY`, and server-only `SUPABASE_SECRET_KEY`. Job/AI keys remain
optional. The Supabase secret key must never appear in browser JavaScript.
Set `INACTIVITY_DELETION_ENABLED=false` until a separately consented warning-email
service is operational; in-app warnings alone cannot reach a user who has stopped visiting.

## Go-live acceptance tests

- User A cannot read, update or delete User B's profile, resume, evidence, sources, matches,
  applications, notifications or storage objects.
- Signed-out requests cannot access private API routes.
- Uploads reject unsupported types and files above 10 MB.
- Account export and deletion affect only the signed-in user.
- Scheduler rejects missing/wrong secrets and succeeds with the correct secret.
- Backups restore in staging; logs contain no secrets or resume text.
- HTTPS, password reset, email verification and rate limiting work.

Do not publish the link until every item passes.
