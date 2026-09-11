import asyncio
import json
from datetime import datetime, timedelta, timezone

from backend.db.local import connection, execute, now, rows, uid
from backend.jobs.matcher import match_job
from backend.jobs.providers import canonical_key, fetch_jobs, fingerprint


def profile_for_matching(profile: dict) -> dict:
    pid=profile["id"]
    evidence=rows("SELECT verification_status,COUNT(*) n FROM career_evidence WHERE profile_id=? GROUP BY verification_status",(pid,))
    counts={x["verification_status"]:x["n"] for x in evidence}; total=sum(counts.values())
    profile["verified_evidence_ratio"]=counts.get("verified",0)/total if total else 0
    profile["qualified_score"]=70; profile["review_score"]=55
    return profile


def recalculate(profile: dict) -> None:
    p=profile_for_matching(profile)
    pid=profile["id"]
    # One transaction avoids opening two SQLite connections for every job.
    with connection() as db:
        jobs=[dict(x) for x in db.execute("SELECT * FROM jobs WHERE is_active=1")]
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
    for source,jobs,fetch_error in fetched:
        source_count=0
        source_duplicates=0
        source_started=datetime.now(timezone.utc)
        try:
            if fetch_error:raise fetch_error
            for item in jobs:
                d=item.dict(); fp=fingerprint(d["company"],d["title"],d["location"],d["description"]);canonical=canonical_key(d["company"],d["title"],d["location"])
                old=rows("SELECT id,fingerprint FROM jobs WHERE source_key=?",(d["source_key"],))
                if old:
                    repost=1 if old[0].get("fingerprint") and old[0]["fingerprint"]!=fp else 0
                    execute("UPDATE jobs SET title=?,company=?,location=?,description=?,url=?,posted_at=?,date_semantics=?,employment_type=?,raw_json=?,fingerprint=?,canonical_key=?,last_seen_at=?,is_active=1,liveness_status='live',repost_count=repost_count+? WHERE source_key=?",(d["title"],d["company"],d["location"],d["description"],d["url"],d["posted_at"],d["date_semantics"],d["employment_type"],json.dumps(d["raw_json"] or {}),fp,canonical,now(),repost,d["source_key"]));updated+=1
                else:
                    duplicate=rows("SELECT id,provider,posted_at FROM jobs WHERE canonical_key=? AND is_active=1 ORDER BY CASE WHEN provider IN ('greenhouse','lever','ashby','smartrecruiters','recruitee') THEN 0 ELSE 1 END,posted_at DESC LIMIT 1",(canonical,))
                    if duplicate:
                        jid=duplicate[0]["id"];source_duplicates+=1;duplicate_total+=1
                        execute("UPDATE jobs SET duplicate_count=duplicate_count+1,last_seen_at=? WHERE id=?",(now(),jid))
                        execute("INSERT OR REPLACE INTO job_source_refs (id,job_id,provider,source_key,source_name,url,first_seen_at,last_seen_at) VALUES (COALESCE((SELECT id FROM job_source_refs WHERE provider=? AND source_key=?),?),?,?,?,?,?,?,?)",(d["provider"],d["source_key"],uid(),jid,d["provider"],d["source_key"],d["source_name"],d["url"],now(),now()))
                    else:
                        jid=uid();execute("INSERT INTO jobs (id,source_key,provider,source_name,title,company,location,description,url,posted_at,first_seen_at,date_semantics,employment_type,is_active,raw_json,fingerprint,last_seen_at,liveness_status,canonical_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,d["source_key"],d["provider"],d["source_name"],d["title"],d["company"],d["location"],d["description"],d["url"],d["posted_at"],now(),d["date_semantics"],d["employment_type"],1,json.dumps(d["raw_json"] or {}),fp,now(),"live",canonical));added+=1
                        execute("INSERT INTO job_source_refs VALUES (?,?,?,?,?,?,?,?)",(uid(),jid,d["provider"],d["source_key"],d["source_name"],d["url"],now(),now()))
                source_count+=1
            duration=(datetime.now(timezone.utc)-source_started).total_seconds()*1000
            execute("UPDATE job_sources SET last_scan_at=?,last_success_at=?,last_error='',jobs_found=?,last_duration_ms=?,last_status='healthy',consecutive_failures=0,cooldown_until=NULL,duplicates_found=? WHERE id=?",(now(),now(),source_count,duration,source_duplicates,source["id"]))
        except Exception as exc:
            message=str(exc)[:300]; errors.append({"source":source["name"],"error":message})
            duration=(datetime.now(timezone.utc)-source_started).total_seconds()*1000
            failures=int(source.get("consecutive_failures") or 0)+1;cooldown=(datetime.now(timezone.utc)+timedelta(minutes=min(60,2**min(failures,5)))).isoformat()
            execute("UPDATE job_sources SET last_scan_at=?,last_error=?,last_duration_ms=?,last_status='failed',consecutive_failures=consecutive_failures+1,cooldown_until=? WHERE id=?",(now(),message,duration,cooldown,source["id"]))
    recalculate(profile)
    source_total=len(sources)
    execute("UPDATE scan_runs SET finished_at=?,new_jobs=?,updated_jobs=?,errors=?,status=?,sources_scanned=?,jobs_found=? WHERE id=?",(now(),added,updated,json.dumps(errors),"partial" if errors else "completed",source_total,added+updated,run_id))
    if added:
        execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"jobs","New jobs discovered",f"{added} new jobs were collected and evaluated.",run_id,0,now(),pid))
    if errors:
        execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"source_error","Some sources need attention",f"{len(errors)} sources could not be scanned.",run_id,0,now(),pid))
    return {"run_id":run_id,"new_jobs":added,"updated_jobs":updated,"duplicates":duplicate_total,"errors":errors}
