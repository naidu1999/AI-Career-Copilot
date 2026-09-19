"""Whole-database snapshot persistence for ephemeral hosts.

Free hosts (Hugging Face Spaces and similar) wipe local disk on restart.
This module keeps Karna OS alive there:

- ``upload_snapshot`` gzips the SQLite database and stores it in a private
  Supabase Storage bucket, keeping only the newest ``SNAPSHOT_KEEP`` files.
- ``restore_latest_snapshot`` pulls the newest snapshot back into place at
  boot so the Space resumes with all its data.
- ``snapshot_loop`` repeats uploads on a timer while the app runs, and
  ``shutdown_snapshot`` captures one final state when the process stops.

Supabase Storage speaks a small REST surface (S3-compatible gateways exist,
but plain HTTP + the service key needs no extra dependency beyond httpx).
"""
import gzip
import io
import logging
import time
from pathlib import Path

import httpx

from backend.core.config_new import settings

LOG = logging.getLogger("karna.snapshots")
SNAPSHOT_NAME = "karna_os.db.gz"


def _conf() -> tuple[str, str, str]:
    """(supabase url, service key, bucket) — empty url means disabled."""
    url = settings.SUPABASE_URL.rstrip("/")
    key = settings.SUPABASE_SECRET_KEY
    if not settings.SNAPSHOT_ENABLED or not url or not key:
        return "", "", ""
    return url, key, settings.SNAPSHOT_BUCKET.strip("/") or "karna-snapshots"


def configured() -> bool:
    return bool(_conf()[0])


def _gzip_database() -> bytes:
    source = settings.database_file
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
        gz.write(source.read_bytes())
    return buf.getvalue()


def _bucket_url(url: str, bucket: str) -> str:
    return f"{url}/storage/v1/object/{bucket}"


def upload_snapshot() -> dict:
    """Gzip the live database into Supabase Storage; rotate old snapshots."""
    url, key, bucket = _conf()
    if not url:
        return {"uploaded": False, "reason": "disabled"}
    if not settings.database_file.exists():
        return {"uploaded": False, "reason": "no database yet"}
    try:
        payload = _gzip_database()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/gzip",
                   "x-upsert": "true", "Cache-Control": "no-store"}
        with httpx.Client(timeout=httpx.Timeout(120)) as client:
            upsert = client.post(f"{_bucket_url(url, bucket)}/latest", headers=headers, content=payload)
            if upsert.status_code in (400, 404):  # bucket missing -> create once, retry
                client.post(f"{url}/storage/v1/bucket", headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"}, json={"id": bucket, "name": bucket, "public": False})
                upsert = client.post(f"{_bucket_url(url, bucket)}/latest", headers=headers, content=payload)
            upsert.raise_for_status()
            client.post(f"{_bucket_url(url, bucket)}/{stamp}", headers=headers, content=payload)
            listed = client.get(f"{url}/storage/v1/object/list/{bucket}",
                                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                json={"prefix": "", "limit": 100, "sortBy": {"column": "created_at", "order": "desc"}})
            stale = []
            if listed.status_code == 200:
                names = [x.get("name") for x in listed.json() if x.get("name") and x["name"] != "latest"]
                for name in names[settings.SNAPSHOT_KEEP:]:
                    stale.append(name)
                    client.delete(f"{_bucket_url(url, bucket)}/{name}", headers={"Authorization": f"Bearer {key}"})
        LOG.info("snapshot uploaded (%.1f KB compressed)", len(payload) / 1024)
        return {"uploaded": True, "bytes": len(payload), "pruned": stale}
    except Exception as exc:
        LOG.warning("snapshot upload failed: %s", str(exc)[:200])
        return {"uploaded": False, "reason": str(exc)[:200]}


def restore_latest_snapshot() -> dict:
    """Download the newest snapshot over the local database file.

    Returns a dict; ``restored`` is False when nothing was available (fresh
    deploy) — the app then simply starts clean and the first upload seeds
    the bucket.
    """
    url, key, bucket = _conf()
    if not url:
        return {"restored": False, "reason": "disabled"}
    try:
        with httpx.Client(timeout=httpx.Timeout(120)) as client:
            response = client.get(f"{_bucket_url(url, bucket)}/latest",
                                  headers={"Authorization": f"Bearer {key}"})
            if response.status_code == 400 or response.status_code == 404:
                return {"restored": False, "reason": "no snapshot yet"}
            response.raise_for_status()
            blob = gzip.decompress(response.content)
        target = settings.database_file
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".db.restore")
        tmp.write_bytes(blob)
        tmp.replace(target)
        LOG.info("snapshot restored (%.1f KB raw)", len(blob) / 1024)
        return {"restored": True, "bytes": len(blob)}
    except Exception as exc:
        LOG.warning("snapshot restore failed: %s", str(exc)[:200])
        return {"restored": False, "reason": str(exc)[:200]}


async def snapshot_loop() -> None:
    """Upload a snapshot every SNAPSHOT_INTERVAL_MINUTES until cancelled."""
    interval = max(5, settings.SNAPSHOT_INTERVAL_MINUTES) * 60
    while True:
        await __import__("asyncio").sleep(interval)
        upload_snapshot()


def shutdown_snapshot() -> None:
    """Best-effort final upload when the process is stopping."""
    try:
        upload_snapshot()
    except Exception:
        pass
