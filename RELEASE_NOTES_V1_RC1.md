# Karna OS v1.0 RC1

- SQLite WAL mode, busy timeout, nine workload indexes and bounded job/evidence queries.
- Match recalculation reduced from multiple connections per job to one transaction.
- Up to four enabled job sources fetched concurrently with isolated failures.
- Evidence updates run match recalculation in the background; bulk actions recalculate once.
- Docker, Compose, non-root runtime, container health check and Render starter blueprint.
- Protected external scheduler endpoint and production preflight secret scan.
- GitHub Actions quality workflow.
- Supabase hosted schema with per-user RLS, private resume storage, indexes and lifecycle fields.
- Deployment security checklist and explicit multi-user go-live gate.

RC1 is the final account-independent engineering package. Public multi-user activation
remains blocked until the owner connects Supabase/hosting accounts and the authenticated
repository adapter passes the isolation acceptance tests.
