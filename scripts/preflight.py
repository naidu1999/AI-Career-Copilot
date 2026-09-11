"""Fail-fast release/deployment checks. This script never prints secret values."""
import os
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
failures=[]

required=["backend/main.py","backend/static/index.html","backend/static/app-v11.js","database/003_v1_hosted.sql","database/004_v11_continuity.sql","Dockerfile"]
for name in required:
    if not (ROOT/name).is_file():failures.append(f"missing required file: {name}")

# Dev machines legitimately keep .env and the local database; the rule is that they
# must never be *packaged*. If a distribution ZIP exists, inspect its contents.
import zipfile
zip_path=ROOT/"dist"/"karna_os.zip"
if zip_path.exists():
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                base=name.rsplit("/",1)[-1]
                if base in {".env"} or base.endswith((".db",".db-shm",".db-wal")):
                    failures.append(f"private runtime file packaged in {zip_path.name}: {name}")
    except zipfile.BadZipFile:
        failures.append(f"unreadable distribution zip: {zip_path.name}")

secret_patterns=(re.compile(r"sb_secret_[A-Za-z0-9_-]+"),re.compile(r"sk-[A-Za-z0-9]{16,}"),re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),re.compile(r"sk-or-[A-Za-z0-9_-]{16,}"))
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() in {".zip",".webp",".png",".jpg",".jpeg",".pdf"}:continue
    if any(part in {".venv","venv",".git"} for part in path.parts):continue
    text=path.read_text(encoding="utf-8",errors="ignore")
    if any(p.search(text) for p in secret_patterns):failures.append(f"possible secret in {path.relative_to(ROOT)}")

if os.getenv("APP_ENV")=="production":
    for key in ("PUBLIC_BASE_URL","CRON_SECRET","SUPABASE_URL","SUPABASE_PUBLISHABLE_KEY","SUPABASE_SECRET_KEY"):
        if not os.getenv(key):failures.append(f"production variable missing: {key}")
    if os.getenv("DEPLOYMENT_MODE")!="hosted":failures.append("production DEPLOYMENT_MODE must be hosted")

if failures:
    print("PREFLIGHT FAILED")
    for item in failures:print(f"- {item}")
    sys.exit(1)
print("PREFLIGHT PASSED")
