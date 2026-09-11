"""Build a distributable ZIP of Karna OS.

Excludes development-only content (virtual envs, caches, local databases,
uploads, backups, exports, secrets) and sanitizes `.env.example` so no API
keys or credentials ship with the archive.

Usage: python scripts/make_zip.py [output.zip]
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "dist" / "karna_os.zip"

EXCLUDED_DIRS = {
    ".venv", "venv", "__pycache__", ".pytest_cache", ".git", ".github",
    ".freebuff", "node_modules", "dist", "build",
}
EXCLUDED_DIR_PARTS = {"data/backups", "data/exports", "data/uploads"}
EXCLUDED_FILES = {".env", ".dockerignore"}
EXCLUDED_SUFFIXES = {".db", ".db-shm", ".db-wal", ".pyc", ".pyo"}

# Anything that looks like an assigned credential is blanked in .env.example.
SECRET_PATTERNS = (
    re.compile(r"^(?P<key>[A-Z0-9_]*(?:KEY|SECRET|PASSWORD|TOKEN)[A-Z0-9_]*)\s*=\s*\S+\s*$"),
)
# URLs that embed credentials (postgres://user:pass@host ...).
CRED_URL = re.compile(r"^(\w+)\s*=\s*\w+(?:\+\w+)?://[^:@/\s]+:[^@/\s]+@(.*)$")


def sanitize_env_example(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if CRED_URL.match(line):
            lines.append(f"{key}=")
        elif any(p.match(stripped) for p in SECRET_PATTERNS):
            lines.append(f"{key}=")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    if "/".join(rel.parts[:2]) in EXCLUDED_DIR_PARTS:
        return True
    if path.is_file():
        if path.name in EXCLUDED_FILES:
            return True
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            return True
    return False


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in ROOT.rglob("*")
        if p.is_file() and not excluded(p)
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = Path("karna_os") / path.relative_to(ROOT)
            if path.name == ".env.example":
                zf.writestr(str(arcname), sanitize_env_example(path.read_text(encoding="utf-8")))
            else:
                zf.write(path, str(arcname))

    size_kb = output.stat().st_size / 1024
    print(f"Wrote {output} ({size_kb:.0f} KB, {len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
