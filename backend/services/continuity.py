"""Cloud mirror continuity. SQLite remains authoritative in personal-local mode."""
import json
from datetime import datetime, timedelta, timezone

from backend.core.config_new import settings
from backend.db.local import execute, now, rows, uid

def enqueue(owner_id:str,entity_type:str,entity_id:str,operation:str,payload:dict)->str:
    item_id=uid();stamp=now()
    execute("INSERT INTO sync_outbox VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(item_id,owner_id,entity_type,entity_id,operation,json.dumps(payload,default=str),1,"pending",0,None,"",stamp,stamp))
    return item_id

def status(owner_id:str)->dict:
    counts=rows("SELECT status,COUNT(*) count FROM sync_outbox WHERE owner_id=? GROUP BY status",(owner_id,))
    return {"enabled":settings.CLOUD_SYNC_ENABLED,"primary_configured":bool(settings.SUPABASE_DATABASE_URL),
            "secondary_configured":bool(settings.SECONDARY_DATABASE_URL),"queue":{x["status"]:x["count"] for x in counts},
            "mode":"local-authoritative"}

def _mirror(url:str,item:dict)->None:
    import psycopg
    with psycopg.connect(url,connect_timeout=8) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS karna_sync_records (
          owner_id text NOT NULL, entity_type text NOT NULL, entity_id text NOT NULL,
          operation text NOT NULL, payload jsonb NOT NULL, version integer NOT NULL,
          updated_at timestamptz NOT NULL, PRIMARY KEY(owner_id,entity_type,entity_id))""")
        db.execute("""INSERT INTO karna_sync_records VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
          ON CONFLICT(owner_id,entity_type,entity_id) DO UPDATE SET operation=excluded.operation,
          payload=excluded.payload,version=excluded.version,updated_at=excluded.updated_at
          WHERE karna_sync_records.version<=excluded.version""",
          (item["owner_id"],item["entity_type"],item["entity_id"],item["operation"],item["payload"],item["version"],now()))

def sync_pending(owner_id:str)->dict:
    if not settings.CLOUD_SYNC_ENABLED:return {"synced":0,"failed":0,"provider":"disabled"}
    pending=rows("SELECT * FROM sync_outbox WHERE owner_id=? AND status IN ('pending','retry') AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY created_at LIMIT 100",(owner_id,now()))
    synced=failed=0;used=""
    for item in pending:
        errors=[]
        for name,url in (("supabase",settings.SUPABASE_DATABASE_URL),("secondary",settings.SECONDARY_DATABASE_URL)):
            if not url:continue
            try:_mirror(url,item);used=name;execute("UPDATE sync_outbox SET status='synced',updated_at=?,last_error='' WHERE id=?",(now(),item["id"]));synced+=1;break
            except Exception as exc:errors.append(f"{name}: {str(exc)[:160]}")
        else:
            failed+=1;attempts=item["attempts"]+1;delay=min(3600,2**min(attempts,10))
            execute("UPDATE sync_outbox SET status='retry',attempts=?,next_attempt_at=?,last_error=?,updated_at=? WHERE id=?",(attempts,(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(),"; ".join(errors) or "No cloud database configured",now(),item["id"]))
    return {"synced":synced,"failed":failed,"provider":used}
