import json
import hashlib
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from backend.core.config_new import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
 id TEXT PRIMARY KEY, full_name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
 target_titles TEXT NOT NULL DEFAULT '[]', skills TEXT NOT NULL DEFAULT '[]',
 locations TEXT NOT NULL DEFAULT '[]', remote_allowed INTEGER NOT NULL DEFAULT 1,
 excluded_roles TEXT NOT NULL DEFAULT '[]', excluded_employment_types TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resumes (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, file_name TEXT NOT NULL, file_type TEXT NOT NULL,
 file_size INTEGER NOT NULL, file_hash TEXT NOT NULL, storage_path TEXT NOT NULL,
 extracted_text TEXT NOT NULL, structured_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(profile_id, file_hash)
);
CREATE TABLE IF NOT EXISTS career_evidence (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, resume_id TEXT NOT NULL, category TEXT NOT NULL,
 normalized_value TEXT NOT NULL, original_text TEXT NOT NULL, confidence REAL NOT NULL,
 verification_status TEXT NOT NULL DEFAULT 'unverified', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_sources (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, provider TEXT NOT NULL, board_key TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'default',
 UNIQUE(owner_id, provider, board_key)
);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, provider TEXT NOT NULL, source_name TEXT NOT NULL,
 title TEXT NOT NULL, company TEXT NOT NULL, location TEXT NOT NULL, description TEXT NOT NULL,
 url TEXT NOT NULL, posted_at TEXT, first_seen_at TEXT NOT NULL, date_semantics TEXT NOT NULL,
 employment_type TEXT NOT NULL DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1,
 raw_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS job_matches (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, job_id TEXT NOT NULL, score REAL NOT NULL,
 matched_skills TEXT NOT NULL, missing_skills TEXT NOT NULL, reasons TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(profile_id, job_id)
);
CREATE TABLE IF NOT EXISTS applications (
 id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, job_id TEXT NOT NULL, status TEXT NOT NULL,
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(profile_id, job_id)
);
CREATE TABLE IF NOT EXISTS application_events (
 id TEXT PRIMARY KEY, application_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_runs (
 id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, trigger TEXT NOT NULL,
 new_jobs INTEGER NOT NULL DEFAULT 0, updated_jobs INTEGER NOT NULL DEFAULT 0,
 errors TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'running',
 sources_scanned INTEGER NOT NULL DEFAULT 0, jobs_found INTEGER NOT NULL DEFAULT 0, owner_id TEXT NOT NULL DEFAULT 'default'
);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
 related_id TEXT, is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'default'
);
CREATE TABLE IF NOT EXISTS evidence_history (
 id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, old_value TEXT, new_value TEXT,
 old_status TEXT, new_status TEXT, changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generated_artifacts (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
 model TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'default'
);
CREATE TABLE IF NOT EXISTS job_source_refs (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL, provider TEXT NOT NULL, source_key TEXT NOT NULL,
 source_name TEXT NOT NULL, url TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 UNIQUE(provider,source_key)
);
CREATE TABLE IF NOT EXISTS sync_outbox (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
 operation TEXT NOT NULL, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at TEXT, last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ai_providers (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'default', name TEXT NOT NULL, adapter TEXT NOT NULL,
 base_url TEXT NOT NULL, api_key_env TEXT NOT NULL DEFAULT '', model TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, is_local INTEGER NOT NULL DEFAULT 0, is_paid INTEGER NOT NULL DEFAULT 0,
 priority INTEGER NOT NULL DEFAULT 100, health_status TEXT NOT NULL DEFAULT 'unknown',
 consecutive_failures INTEGER NOT NULL DEFAULT 0, cooldown_until TEXT, last_success_at TEXT,
 last_failure_at TEXT, last_error TEXT NOT NULL DEFAULT '', average_latency_ms REAL NOT NULL DEFAULT 0,
 requests INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 UNIQUE(owner_id,name)
);
CREATE TABLE IF NOT EXISTS ai_routes (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL DEFAULT 'default', task TEXT NOT NULL,
 provider_ids TEXT NOT NULL DEFAULT '[]', mode TEXT NOT NULL DEFAULT 'automatic',
 allow_paid INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 4,
 updated_at TEXT NOT NULL, UNIQUE(owner_id,task)
);
CREATE TABLE IF NOT EXISTS ai_request_log (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, task TEXT NOT NULL, provider_id TEXT,
 model TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, latency_ms REAL NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 1, fallback_reason TEXT NOT NULL DEFAULT '',
 error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interview_prep (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, job_id TEXT NOT NULL, question TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT 'general', answer_framework TEXT NOT NULL DEFAULT '',
 star_situation TEXT NOT NULL DEFAULT '', star_task TEXT NOT NULL DEFAULT '',
 star_action TEXT NOT NULL DEFAULT '', star_result TEXT NOT NULL DEFAULT '',
 completed INTEGER NOT NULL DEFAULT 0, confidence INTEGER NOT NULL DEFAULT 0,
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backup_records (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, path TEXT NOT NULL, size_bytes INTEGER NOT NULL,
 checksum TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'verified', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hidden_jobs (
 owner_id TEXT NOT NULL, job_id TEXT NOT NULL, hidden_at TEXT NOT NULL, PRIMARY KEY(owner_id,job_id)
);
CREATE TABLE IF NOT EXISTS fit_dossiers (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, job_id TEXT NOT NULL,
 global_score REAL NOT NULL DEFAULT 0, verdict TEXT NOT NULL DEFAULT '',
 dimensions TEXT NOT NULL DEFAULT '{}', requirement_weights TEXT NOT NULL DEFAULT '[]',
 legitimacy TEXT NOT NULL DEFAULT '{}', interview_focus TEXT NOT NULL DEFAULT '[]',
 recommended_actions TEXT NOT NULL DEFAULT '[]', model TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'ai', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fit_dossiers_job ON fit_dossiers(owner_id,job_id,created_at);
CREATE TABLE IF NOT EXISTS story_bank (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT 'general', situation TEXT NOT NULL DEFAULT '',
 task TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
 result TEXT NOT NULL DEFAULT '', reflection TEXT NOT NULL DEFAULT '',
 tags TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'draft',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_evidence_profile_status ON career_evidence(profile_id,verification_status);
CREATE INDEX IF NOT EXISTS idx_evidence_resume ON career_evidence(resume_id);
CREATE INDEX IF NOT EXISTS idx_jobs_active_posted ON jobs(is_active,posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_provider ON jobs(provider,is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_matches_profile_class_score ON job_matches(profile_id,classification,score DESC);
CREATE INDEX IF NOT EXISTS idx_applications_profile_status ON applications(profile_id,archived,status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(is_read,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_runs_started ON scan_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sources_owner ON job_sources(owner_id,enabled,name);
CREATE INDEX IF NOT EXISTS idx_notifications_owner ON notifications(owner_id,is_read,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scans_owner ON scan_runs(owner_id,started_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifacts_owner ON generated_artifacts(owner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_refs_job ON job_source_refs(job_id,last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON sync_outbox(status,next_attempt_at,created_at);
CREATE INDEX IF NOT EXISTS idx_ai_provider_health ON ai_providers(owner_id,enabled,health_status,priority);
CREATE INDEX IF NOT EXISTS idx_ai_log_owner ON ai_request_log(owner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interview_job ON interview_prep(owner_id,job_id,completed);
CREATE INDEX IF NOT EXISTS idx_hidden_jobs_owner ON hidden_jobs(owner_id,hidden_at DESC);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    path = settings.database_file
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path,timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize() -> None:
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript(SCHEMA)
        # Idempotent v0.3 migrations for databases created by v0.2.
        profile_migrations = {
            "country": "TEXT NOT NULL DEFAULT 'India'",
            "remote_countries": "TEXT NOT NULL DEFAULT '[\"India\"]'",
            "years_experience": "REAL NOT NULL DEFAULT 0",
            "minimum_match_score": "REAL NOT NULL DEFAULT 55",
            "current_employer": "TEXT NOT NULL DEFAULT ''",
            "current_role": "TEXT NOT NULL DEFAULT ''",
            "phone": "TEXT NOT NULL DEFAULT ''",
            "portfolio_url": "TEXT NOT NULL DEFAULT ''",
            "linkedin_url": "TEXT NOT NULL DEFAULT ''",
            "location_current": "TEXT NOT NULL DEFAULT ''",
            "relevant_experience": "REAL NOT NULL DEFAULT 0",
            "work_authorization": "TEXT NOT NULL DEFAULT 'India'",
            "needs_sponsorship": "INTEGER NOT NULL DEFAULT 0",
            "notice_period_days": "INTEGER NOT NULL DEFAULT 45",
            "expected_compensation": "TEXT NOT NULL DEFAULT '8-12 LPA'",
            "preferred_industries": "TEXT NOT NULL DEFAULT '[]'",
            "preferred_employment_types": "TEXT NOT NULL DEFAULT '[\"full-time\"]'",
            "last_active_at": "TEXT",
            "first_warning_at": "TEXT",
            "final_warning_at": "TEXT",
            "deletion_scheduled_at": "TEXT",
        }
        evidence_migrations = {
            "source_section": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT",
        }
        source_migrations = {
            "owner_id": "TEXT NOT NULL DEFAULT 'default'",
            "last_scan_at": "TEXT",
            "last_success_at": "TEXT",
            "last_error": "TEXT NOT NULL DEFAULT ''",
            "jobs_found": "INTEGER NOT NULL DEFAULT 0",
            "last_duration_ms": "REAL NOT NULL DEFAULT 0",
            "last_status": "TEXT NOT NULL DEFAULT 'never'",
            "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
            "cooldown_until": "TEXT",
            "duplicates_found": "INTEGER NOT NULL DEFAULT 0",
        }
        job_migrations = {
            "fingerprint": "TEXT NOT NULL DEFAULT ''",
            "last_seen_at": "TEXT",
            "liveness_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "closed_at": "TEXT",
            "repost_count": "INTEGER NOT NULL DEFAULT 0",
            "work_mode": "TEXT NOT NULL DEFAULT ''",
            "canonical_key": "TEXT NOT NULL DEFAULT ''",
            "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
        }
        match_migrations = {
            "classification": "TEXT NOT NULL DEFAULT 'review'",
            "components": "TEXT NOT NULL DEFAULT '{}'",
            "blockers": "TEXT NOT NULL DEFAULT '[]'",
            "matcher_version": "TEXT NOT NULL DEFAULT '4.0'",
        }
        application_migrations = {
            "recruiter_name": "TEXT NOT NULL DEFAULT ''",
            "recruiter_contact": "TEXT NOT NULL DEFAULT ''",
            "follow_up_at": "TEXT",
            "interview_at": "TEXT",
            "archived": "INTEGER NOT NULL DEFAULT 0",
            "deadline_at": "TEXT",
            "rejection_reason": "TEXT NOT NULL DEFAULT ''",
            "salary_details": "TEXT NOT NULL DEFAULT ''",
            "offer_details": "TEXT NOT NULL DEFAULT ''",
        }
        scan_migrations = {"status":"TEXT NOT NULL DEFAULT 'running'","sources_scanned":"INTEGER NOT NULL DEFAULT 0","jobs_found":"INTEGER NOT NULL DEFAULT 0","owner_id":"TEXT NOT NULL DEFAULT 'default'"}
        notification_migrations={"owner_id":"TEXT NOT NULL DEFAULT 'default'"}
        artifact_migrations={"owner_id":"TEXT NOT NULL DEFAULT 'default'","status":"TEXT NOT NULL DEFAULT 'draft'","approved_at":"TEXT","parent_id":"TEXT","metadata":"TEXT NOT NULL DEFAULT '{}'"}
        story_migrations={"owner_id":"TEXT NOT NULL DEFAULT 'default'","updated_at":"TEXT"}
        for table, migrations in (("profiles",profile_migrations),("career_evidence",evidence_migrations),("job_sources",source_migrations),("jobs",job_migrations),("job_matches",match_migrations),("applications",application_migrations),("scan_runs",scan_migrations),("notifications",notification_migrations),("generated_artifacts",artifact_migrations),("story_bank",story_migrations)):
            columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, declaration in migrations.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        db.executescript(INDEXES)
        # Very old databases carried a table-wide UNIQUE(provider, board_key) on
        # job_sources, which blocks a second profile from using the same boards.
        # Rebuild the table with the per-owner constraint when the old one is
        # detected. SQLite cannot drop constraints, so the rows are copied.
        refs_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='job_sources'").fetchone()
        if refs_sql and re.search(r"UNIQUE\s*\(\s*provider\s*,\s*board_key\s*\)", refs_sql[0] or "", re.I):
            legacy_cols = [r[1] for r in db.execute("PRAGMA table_info(job_sources)").fetchall()]
            select_cols = ", ".join(legacy_cols)
            insert_cols = select_cols
            if "last_duration_ms" not in legacy_cols: legacy_cols.append("last_duration_ms")
            db.execute("ALTER TABLE job_sources RENAME TO job_sources_legacy")
            db.executescript(SCHEMA)
            db.execute(f"INSERT INTO job_sources ({insert_cols}, last_duration_ms) SELECT {select_cols}, 0 FROM job_sources_legacy")
            db.execute("DROP TABLE job_sources_legacy")
            db.execute("DELETE FROM job_source_refs WHERE job_id NOT IN (SELECT id FROM jobs)")
        count = db.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        if not count:
            ts = now()
            db.execute(
                "INSERT INTO profiles (id,full_name,email,target_titles,skills,locations,remote_allowed,excluded_roles,excluded_employment_types,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("default", "", "", json.dumps(["AI/ML Engineer", "Data Scientist", "Data Analyst", "Data Engineer", "NLP/GenAI Engineer", "Computer Vision Engineer"]), json.dumps([]), json.dumps(["Bengaluru", "Hyderabad", "Chennai", "Remote"]), 1, json.dumps(["BPO", "Sales", "Support", "Internship"]), json.dumps(["contract", "internship"]), ts, ts),
            )


def backup() -> str:
    source = settings.database_file
    if not source.exists():
        return ""
    directory = Path(settings.BACKUP_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = directory / f"karna-os-{stamp}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return str(target)

def backup_info(path:str)->dict:
    file=Path(path)
    digest=hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else ""
    return {"path":str(file),"size_bytes":file.stat().st_size if file.is_file() else 0,"checksum":digest}

def verify_backup(path:str)->dict:
    file=Path(path)
    if not file.is_file():raise FileNotFoundError("Backup does not exist")
    with sqlite3.connect(file) as db:
        result=db.execute("PRAGMA integrity_check").fetchone()[0]
    return {**backup_info(path),"valid":result=="ok","integrity":result}

def restore_backup(path:str)->None:
    source=Path(path).resolve();directory=Path(settings.BACKUP_DIR).resolve()
    if not source.is_file() or source.parent!=directory:raise ValueError("Backup must be selected from the configured backup directory")
    check=verify_backup(str(source))
    if not check["valid"]:raise ValueError("Backup integrity check failed")
    current=settings.database_file
    current.parent.mkdir(parents=True,exist_ok=True)
    safety=backup() if current.exists() else ""
    with sqlite3.connect(source) as src, sqlite3.connect(current) as dst:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    initialize()
    if safety and not Path(safety).exists():raise RuntimeError("Safety backup was not created")

def list_backups()->list[dict]:
    directory=Path(settings.BACKUP_DIR);directory.mkdir(parents=True,exist_ok=True)
    return [backup_info(str(x))|{"created_at":datetime.fromtimestamp(x.stat().st_mtime,timezone.utc).isoformat()} for x in sorted(directory.glob("karna-os-*.db"),reverse=True)]

def rotate_backups()->int:
    """Keep bounded daily/weekly/monthly generations without deleting the newest copy."""
    files=sorted(Path(settings.BACKUP_DIR).glob("karna-os-*.db"),key=lambda x:x.stat().st_mtime,reverse=True)
    keep=set(files[:settings.BACKUP_DAILY_RETENTION]);weekly=set();monthly=set()
    for file in files:
        dt=datetime.fromtimestamp(file.stat().st_mtime,timezone.utc)
        if len(weekly)<settings.BACKUP_WEEKLY_RETENTION:weekly.add((dt.isocalendar().year,dt.isocalendar().week))
        if len(monthly)<settings.BACKUP_MONTHLY_RETENTION:monthly.add((dt.year,dt.month))
        if (dt.isocalendar().year,dt.isocalendar().week) in weekly or (dt.year,dt.month) in monthly:keep.add(file)
    removed=0
    for file in files:
        if file not in keep:file.unlink();removed+=1
    return removed

def storage_usage()->dict:
    def total(path:Path)->int:return sum(x.stat().st_size for x in path.rglob("*") if x.is_file()) if path.exists() else 0
    return {"database_bytes":settings.database_file.stat().st_size if settings.database_file.exists() else 0,
            "uploads_bytes":total(settings.upload_path),"backups_bytes":total(Path(settings.BACKUP_DIR)),
            "exports_bytes":total(Path("data/exports"))}


def rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with connection() as db:
        return [dict(r) for r in db.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple = ()) -> None:
    # WAL allows one writer at a time; the background re-matcher can hold the
    # write lock for a while, so retry briefly instead of failing the request.
    for attempt in range(10):
        try:
            with connection() as db:
                db.execute(sql, params)
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 9:
                raise
            time.sleep(0.15 * (attempt + 1))


def uid() -> str:
    return str(uuid4())
