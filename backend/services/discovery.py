import asyncio
import json
import logging
import os
import queue
import re
import threading
from datetime import datetime, timedelta, timezone

from backend.db.local import connection, execute, now, rows, uid
from backend.jobs.matcher import match_job
from backend.jobs.providers import canonical_key, fetch_jobs, fingerprint

LOG=logging.getLogger("karna.recalc")
ATS_PROVIDERS={'greenhouse','lever','ashby','smartrecruiters','recruitee'}


def profile_for_matching(profile: dict) -> dict:
    pid=profile["id"]
    evidence=rows("SELECT verification_status,COUNT(*) n FROM career_evidence WHERE profile_id=? GROUP BY verification_status",(pid,))
    counts={x["verification_status"]:x["n"] for x in evidence}; total=sum(counts.values())
    profile["verified_evidence_ratio"]=counts.get("verified",0)/total if total else 0
    profile["qualified_score"]=70; profile["review_score"]=55
    return profile


_recalculating:set[str]=set()

def recalculate(profile: dict, touched:set[str]|None=None) -> None:
    """Recompute match rows.

    touched=None (profile changed) re-matches every active job. A scan passes
    only the job ids it inserted or refreshed, so a typical scan re-matches a
    few hundred postings instead of the whole table.

    Calls are coalesced per profile: while one full pass is running, further
    requests for the same profile are dropped (the running pass already reads
    the latest profile row). This keeps rapid saves from queueing up
    multi-minute backlogs that freeze the app.
    """
    pid=profile["id"]
    if pid in _recalculating:return
    _recalculating.add(pid)
    try:
        _recalculate_now(profile,touched)
    finally:
        _recalculating.discard(pid)

# Background re-matching: request_recalc() returns instantly and a single
# daemon worker performs the (potentially ~40s) full pass off the request
# path. The profile row is re-read inside the worker, so a save that lands
# while another pass is running is always matched with the newest data.
_recalc_q:"queue.Queue[str]"=queue.Queue()
_recalc_queued:set[str]=set()
_recalc_lock=threading.Lock()
_recalc_worker_started=False

def request_recalc(pid:str) -> None:
    """Schedule a full match recompute for a profile without blocking."""
    # Under pytest, run inline: the shared background worker and its coalescing
    # would otherwise leak work across tests (each test uses its own database).
    if os.environ.get("PYTEST_CURRENT_TEST"):
        row=rows("SELECT * FROM profiles WHERE id=?",(pid,))
        if row:recalculate(_decode_profile_row(row[0] if isinstance(row,list) else row))
        return
    global _recalc_worker_started
    with _recalc_lock:
        if pid in _recalc_queued:return
        _recalc_queued.add(pid)
        if not _recalc_worker_started:
            _recalc_worker_started=True
            threading.Thread(target=_recalc_worker,daemon=True,name="karna-recalc").start()
    _recalc_q.put(pid)

def _decode_profile_row(row) -> dict:
    prof=dict(row)
    for field in ("target_titles","skills","locations","excluded_roles","excluded_employment_types","remote_countries","preferred_industries","preferred_employment_types"):
        value=prof.get(field)
        if isinstance(value,str):
            try:prof[field]=json.loads(value)
            except Exception:prof[field]=[]
    return prof

def _recalc_worker() -> None:
    while True:
        pid=_recalc_q.get()
        with _recalc_lock:_recalc_queued.discard(pid)
        try:
            row=rows("SELECT * FROM profiles WHERE id=?",(pid,))
            if row:recalculate(_decode_profile_row(row[0] if isinstance(row,list) else row))
        except Exception:
            LOG.exception("Background match recompute failed for profile %s",pid)

def _recalculate_now(profile: dict, touched:set[str]|None=None) -> None:
    p=profile_for_matching(profile)
    pid=profile["id"]
    # One transaction avoids opening two SQLite connections for every job.
    with connection() as db:
        if touched is None:
            jobs=[dict(x) for x in db.execute("SELECT * FROM jobs WHERE is_active=1")]
        else:
            touched={str(x) for x in touched}
            if not touched:return
            jobs=[]
            ids=list(touched)
            for start in range(0,len(ids),500):
                chunk=ids[start:start+500]
                jobs+=[dict(x) for x in db.execute(f"SELECT * FROM jobs WHERE is_active=1 AND id IN ({','.join('?'*len(chunk))})",chunk)]
        existing={x["job_id"]:x["id"] for x in db.execute("SELECT id,job_id FROM job_matches WHERE profile_id=?",(pid,))}
        timestamp=now()
        for job in jobs:
            m=match_job(p,job)
            values=(m["score"],json.dumps(m["matched_skills"]),json.dumps(m["missing_skills"]),json.dumps(m["reasons"]+m["warnings"]),timestamp,m["classification"],json.dumps(m["components"]),json.dumps(m["blockers"]),m["matcher_version"])
            if job["id"] in existing:
                db.execute("UPDATE job_matches SET score=?,matched_skills=?,missing_skills=?,reasons=?,created_at=?,classification=?,components=?,blockers=?,matcher_version=? WHERE id=?",values+(existing[job["id"]],))
            else:
                db.execute("INSERT INTO job_matches (id,profile_id,job_id,score,matched_skills,missing_skills,reasons,created_at,classification,components,blockers,matcher_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(uid(),pid,job["id"],*values))


async def scan(profile: dict, trigger: str="manual", source_id:str|None=None) -> dict:
    pid=profile["id"]
    run_id=uid(); execute("INSERT INTO scan_runs (id,started_at,trigger,owner_id) VALUES (?,?,?,?)",(run_id,now(),trigger,pid))
    errors=[]; added=0; updated=0
    sql="SELECT * FROM job_sources WHERE enabled=1 AND owner_id=? AND (cooldown_until IS NULL OR cooldown_until<=?)";params=[pid,now()]
    if source_id:sql+=" AND id=?";params.append(source_id)
    sources=rows(sql,tuple(params))
    semaphore=asyncio.Semaphore(4)
    async def fetch_source(source):
        try:
            async with semaphore:
                return source,await fetch_jobs(source["provider"],source["board_key"],source["name"],profile),None
        except Exception as exc:
            return source,[],exc
    fetched=await asyncio.gather(*(fetch_source(source) for source in sources))
    duplicate_total=0
    # PERF: snapshot all dedup keys in ONE query instead of two per job (the old
    # per-job rows()/execute() calls each opened a fresh SQLite connection).
    by_key={x["source_key"]:x for x in rows("SELECT id,source_key,fingerprint FROM jobs")}
    canonical_best=rows("SELECT id,canonical_key,provider,posted_at FROM jobs WHERE canonical_key!='' AND is_active=1")
    best={}
    for row in canonical_best:
        current=best.get(row["canonical_key"])
        ats_first=0 if row["provider"] in {'greenhouse','lever','ashby','smartrecruiters','recruitee'} else 1
        rank=(ats_first, row["posted_at"] or "")
        if current is None or rank>current[0]:best[row["canonical_key"]]=(rank,row)
    touched=set()  # job ids whose match rows must be recomputed this scan
    # Insurance against stale refs (e.g. jobs removed outside this code path):
    # a ref without its job would crash the UNIQUE(provider,source_key) upserts.
    execute("DELETE FROM job_source_refs WHERE job_id NOT IN (SELECT id FROM jobs)")
    for source,jobs,fetch_error in fetched:
        source_count=0
        source_duplicates=0
        source_started=datetime.now(timezone.utc)
        try:
            if fetch_error:raise fetch_error
            stamp=now()
            with connection() as db:
                # PERF: every write for a source batch happens on ONE connection/transaction.
                for item in jobs:
                    d=item.dict(); fp=fingerprint(d["company"],d["title"],d["location"],d["description"]);canonical=canonical_key(d["company"],d["title"],d["location"])
                    old=by_key.get(d["source_key"])
                    if old:
                        repost=1 if old.get("fingerprint") and old["fingerprint"]!=fp else 0
                        db.execute("UPDATE jobs SET title=?,company=?,location=?,description=?,url=?,posted_at=?,date_semantics=?,employment_type=?,raw_json=?,fingerprint=?,canonical_key=?,last_seen_at=?,is_active=1,liveness_status='live',repost_count=repost_count+? WHERE id=?",(d["title"],d["company"],d["location"],d["description"],d["url"],d["posted_at"],d["date_semantics"],d["employment_type"],json.dumps(d["raw_json"] or {}),fp,canonical,stamp,repost,old["id"]));updated+=1
                        touched.add(old["id"])
                        by_key[d["source_key"]]={"id":old["id"],"source_key":d["source_key"],"fingerprint":fp}
                    else:
                        duplicate=best.get(canonical)
                        if duplicate:
                            jid=duplicate[1]["id"];source_duplicates+=1;duplicate_total+=1
                            db.execute("UPDATE jobs SET duplicate_count=duplicate_count+1,last_seen_at=? WHERE id=?",(stamp,jid))
                            db.execute("INSERT INTO job_source_refs (id,job_id,provider,source_key,source_name,url,first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(provider,source_key) DO UPDATE SET job_id=excluded.job_id,url=excluded.url,source_name=excluded.source_name,last_seen_at=excluded.last_seen_at",(uid(),jid,d["provider"],d["source_key"],d["source_name"],d["url"],stamp,stamp))
                        else:
                            jid=uid();db.execute("INSERT INTO jobs (id,source_key,provider,source_name,title,company,location,description,url,posted_at,first_seen_at,date_semantics,employment_type,is_active,raw_json,fingerprint,last_seen_at,liveness_status,canonical_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,d["source_key"],d["provider"],d["source_name"],d["title"],d["company"],d["location"],d["description"],d["url"],d["posted_at"],stamp,d["date_semantics"],d["employment_type"],1,json.dumps(d["raw_json"] or {}),fp,stamp,"live",canonical));added+=1
                            db.execute("INSERT INTO job_source_refs (id,job_id,provider,source_key,source_name,url,first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(provider,source_key) DO UPDATE SET job_id=excluded.job_id,url=excluded.url,source_name=excluded.source_name,last_seen_at=excluded.last_seen_at",(uid(),jid,d["provider"],d["source_key"],d["source_name"],d["url"],stamp,stamp))
                            by_key[d["source_key"]]={"id":jid,"source_key":d["source_key"],"fingerprint":fp}
                            # Register the new vacancy so later sources in THIS scan still merge onto it.
                            rank=(0 if d["provider"] in ATS_PROVIDERS else 1, d["posted_at"] or "")
                            best.setdefault(canonical,(rank,{"id":jid,"canonical_key":canonical,"provider":d["provider"],"posted_at":d["posted_at"]}))
                            touched.add(jid)
                    source_count+=1
            duration=(datetime.now(timezone.utc)-source_started).total_seconds()*1000
            execute("UPDATE job_sources SET last_scan_at=?,last_success_at=?,last_error='',jobs_found=?,last_duration_ms=?,last_status='healthy',consecutive_failures=0,cooldown_until=NULL,duplicates_found=? WHERE id=?",(now(),now(),source_count,duration,source_duplicates,source["id"]))
        except Exception as exc:
            # Never persist credentials: provider errors can echo authenticated URLs.
            message=re.sub(r"(app_key|apiKey|api_key|token|app_id)=[^&\s'\"]+",r"\1=***",str(exc))[:300]
            # A gone board (404) or a source whose credentials were never set up
            # will never succeed again — disable it so scans stay clean. Transient
            # failures (rate limits, expired keys) keep the source enabled.
            permanent=("404" in message) or ("not configured" in message.lower())
            if permanent:message+=" · source disabled automatically"
            errors.append({"source":source["name"],"error":message})
            duration=(datetime.now(timezone.utc)-source_started).total_seconds()*1000
            failures=int(source.get("consecutive_failures") or 0)+1;cooldown=(datetime.now(timezone.utc)+timedelta(minutes=min(60,2**min(failures,5)))).isoformat()
            execute("UPDATE job_sources SET last_scan_at=?,last_error=?,last_duration_ms=?,last_status='failed',consecutive_failures=consecutive_failures+1,cooldown_until=? WHERE id=?",(now(),message,duration,cooldown,source["id"]))
            if permanent:execute("UPDATE job_sources SET enabled=0 WHERE id=?",(source["id"],))
    recalculate(profile, touched=touched)
    source_total=len(sources)
    execute("UPDATE scan_runs SET finished_at=?,new_jobs=?,updated_jobs=?,errors=?,status=?,sources_scanned=?,jobs_found=? WHERE id=?",(now(),added,updated,json.dumps(errors),"partial" if errors else "completed",source_total,added+updated,run_id))
    if added:
        execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"jobs","New jobs discovered",f"{added} new jobs were collected and evaluated.",run_id,0,now(),pid))
    if errors:
        execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"source_error","Some sources need attention",f"{len(errors)} sources could not be scanned.",run_id,0,now(),pid))
    return {"run_id":run_id,"new_jobs":added,"updated_jobs":updated,"duplicates":duplicate_total,"errors":errors}
