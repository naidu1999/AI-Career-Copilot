# Karna OS v1.1 architecture

```mermaid
flowchart TD
 U[Browser] --> A[FastAPI]
 A --> M[Matcher v4]
 A --> L[SQLite + WAL]
 A --> R[AI Router]
 A --> J[Job connectors]
 L --> O[Sync outbox]
 O --> S[Supabase PostgreSQL]
 O --> N[Secondary PostgreSQL]
 R --> C[Authorized cloud AI]
 R --> Q[Local Ollama]
```

SQLite is authoritative in personal mode. All job applications remain human-controlled.
Matching is deterministic; AI explains, writes and coaches but cannot override blockers.
Generated documents require approval before export. Hosted mode adds Supabase Auth,
secure cookies, user-scoped records, RLS contracts and an external scheduler.
