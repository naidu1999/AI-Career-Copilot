# Backup, restore and cloud continuity

Personal mode uses SQLite in WAL mode as the source of truth. **Create backup** uses
SQLite's online backup API and verifies the copy with `PRAGMA integrity_check` plus a
SHA-256 checksum. Restore accepts only a file inside the configured backup directory,
requires the exact confirmation phrase and creates a safety backup first.

Daily scheduling keeps bounded daily, weekly and monthly generations. Copy important
backups to encrypted external storage; free cloud tiers are not a sole recovery plan.

Cloud mirroring uses an outbox. Every supported mutation is committed locally before a
cloud attempt. Supabase PostgreSQL is attempted first; the configured secondary
PostgreSQL endpoint is attempted next. Failed items use exponential retry. This is an
active-passive mirror, not unsafe multi-master switching.
