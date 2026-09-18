import asyncio
import json
import re
import difflib
import io
import time
import logging
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl

from backend.core.config_new import settings
from backend.db.local import backup, backup_info, connection, execute, initialize, list_backups, now, restore_backup, rotate_backups, rows, storage_usage, uid, verify_backup
from backend.jobs.catalog import SEED_SOURCES
from backend.jobs.providers import GLOBAL_PROVIDERS, PROVIDERS, canonical_key, fetch_jobs, key
from backend.services.ai_router import AIRouter, router_status
from backend.services.continuity import enqueue, status as sync_status, sync_pending
from backend.services import linkedin_import
from backend.services.discovery import recalculate, request_recalc, scan
from backend.services.dossier import basic_dossier, dossier_prompt, legitimacy_check, parse_dossier_json
from backend.services.document_service import SUPPORTED, extract_text, file_hash, safe_filename, valid_signature
from backend.services.profile_parser import parse_resume
from backend.services.auth_service import authenticate, current_user_id, delete_auth_user, hosted, password_action, revoke, user_id
from backend.services.recruiter import recruiter_context, senior_recruiter_system_prompt
from backend.services.artifact_export import to_docx, to_pdf

ARRAY_FIELDS=("target_titles","skills","locations","excluded_roles","excluded_employment_types","remote_countries","preferred_industries","preferred_employment_types")

def decode_profile(row):
    for field in ARRAY_FIELDS: row[field]=json.loads(row.get(field) or "[]")
    for field in ("remote_allowed","needs_sponsorship"):row[field]=bool(row.get(field))
    return row

def get_profile_data():
    # PERF: only take the INSERT path when the row is genuinely missing — a write
    # transaction on every GET was locking the database during scans.
    found=rows("SELECT * FROM profiles WHERE id=?",(user_id(),))
    if not found:
        ensure_profile(user_id())
        found=rows("SELECT * FROM profiles WHERE id=?",(user_id(),))
    if not found: raise HTTPException(500,"Career profile was not initialized")
    return decode_profile(found[0])

def ensure_profile(pid:str,email:str=""):
    ts=now();execute("INSERT OR IGNORE INTO profiles (id,full_name,email,target_titles,skills,locations,remote_allowed,excluded_roles,excluded_employment_types,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(pid,"",email,json.dumps(["AI/ML Engineer","Data Scientist","Data Analyst","Data Engineer","NLP/GenAI Engineer","Computer Vision Engineer"]),"[]",json.dumps(["Bengaluru","Hyderabad","Chennai","Remote"]),1,json.dumps(["BPO","Sales","Support","Internship"]),json.dumps(["contract","internship"]),ts,ts))
    # New local workspaces start with the recommended source catalogue so
    # their first scan finds jobs instead of failing on zero sources.
    # Hosted accounts keep the empty-by-default onboarding. API-backed
    # boards enable only when their credentials exist.
    if not hosted() and not rows("SELECT id FROM job_sources WHERE owner_id=? LIMIT 1",(pid,)):
        for name,provider,board,default_enabled in SEED_SOURCES:
            enabled=default_enabled and (provider=="arbeitnow" or provider in {"remotive","remoteok","jobicy","himalayas"} or provider=="adzuna" and bool(settings.ADZUNA_APP_ID) or provider=="jooble" and bool(settings.JOOBLE_API_KEY))
            execute("INSERT INTO job_sources (id,name,provider,board_key,enabled,created_at,owner_id) VALUES (?,?,?,?,?,?,?)",(uid(),name,provider,board,int(enabled),ts,pid))

async def lifecycle_check():
    if not hosted() or not settings.INACTIVITY_DELETION_ENABLED:return
    current=datetime.now(timezone.utc)
    for profile in rows("SELECT id,last_active_at,first_warning_at,final_warning_at,deletion_scheduled_at FROM profiles WHERE id!='default'"):
        last=datetime.fromisoformat(profile["last_active_at"] or now());days=(current-last).days;pid=profile["id"]
        if days>=120 and profile["final_warning_at"] and profile["deletion_scheduled_at"] and datetime.fromisoformat(profile["deletion_scheduled_at"])<=current:
            paths=[Path(x["storage_path"]) for x in rows("SELECT storage_path FROM resumes WHERE profile_id=?",(pid,))]
            with connection() as db:
                app_ids=[x[0] for x in db.execute("SELECT id FROM applications WHERE profile_id=?",(pid,))]
                for aid in app_ids:db.execute("DELETE FROM application_events WHERE application_id=?",(aid,))
                for table,column in (("applications","profile_id"),("job_matches","profile_id"),("career_evidence","profile_id"),("resumes","profile_id"),("job_sources","owner_id"),("notifications","owner_id"),("scan_runs","owner_id"),("generated_artifacts","owner_id"),("ai_providers","owner_id"),("ai_routes","owner_id"),("ai_request_log","owner_id"),("interview_prep","owner_id"),("sync_outbox","owner_id")):db.execute(f"DELETE FROM {table} WHERE {column}=?",(pid,))
                db.execute("DELETE FROM profiles WHERE id=?",(pid,))
            for path in paths:
                if path.is_file() and path.parent.resolve()==settings.upload_path.resolve():path.unlink()
            await delete_auth_user(pid)
        elif days>=113 and not profile["final_warning_at"]:
            execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"deletion_final","Final inactivity warning","Your account is scheduled for deletion in 7 days unless you sign in.",None,0,now(),pid));execute("UPDATE profiles SET final_warning_at=?,deletion_scheduled_at=? WHERE id=?",(now(),(current+timedelta(days=7)).isoformat(),pid))
        elif days>=90 and not profile["first_warning_at"]:
            execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"deletion_warning","Inactivity warning","Your account will be deleted in 30 days unless you sign in.",None,0,now(),pid));execute("UPDATE profiles SET first_warning_at=?,deletion_scheduled_at=? WHERE id=?",(now(),(current+timedelta(days=30)).isoformat(),pid))

async def scheduler_loop():
    while True:
        local=datetime.now(ZoneInfo(settings.TIMEZONE))
        target=local.replace(hour=max(0,min(23,settings.SCAN_HOUR_LOCAL)),minute=0,second=0,microsecond=0)
        if target<=local:target+=timedelta(days=1)
        await asyncio.sleep(max(30,(target-local).total_seconds()))
        try:
            for profile in rows("SELECT * FROM profiles WHERE id!='default'" if hosted() else "SELECT * FROM profiles"):
                await scan(decode_profile(profile),"scheduled")
            await lifecycle_check()
            if not hosted():backup();rotate_backups()
        except Exception as exc:
            execute("INSERT INTO notifications (id,kind,title,message,related_id,is_read,created_at,owner_id) VALUES (?,?,?,?,?,?,?,?)",(uid(),"scheduler_error","Scheduled scan failed",str(exc)[:300],None,0,now(),"default"))

@asynccontextmanager
async def lifespan(_app):
    initialize(); task=asyncio.create_task(scheduler_loop()) if settings.SCAN_ENABLED else None
    yield
    if task: task.cancel()

app=FastAPI(title=settings.APP_NAME,version=settings.APP_VERSION,lifespan=lifespan)
static=Path(__file__).parent/"static"; app.mount("/static",StaticFiles(directory=static),name="static")
REQUEST_WINDOWS=defaultdict(deque)
LOG=logging.getLogger("karna")

PROFILE_COOKIE="karna_profile"

def set_session_cookies(response:Response,data:dict):
    response.set_cookie(settings.SESSION_COOKIE_NAME,data["access_token"],httponly=True,secure=settings.SESSION_COOKIE_SECURE,samesite="lax",max_age=int(data.get("expires_in",3600)),path="/")
    if data.get("refresh_token"):
        response.set_cookie(settings.REFRESH_COOKIE_NAME,data["refresh_token"],httponly=True,secure=settings.SESSION_COOKIE_SECURE,samesite="strict",max_age=60*60*24*30,path="/api/")

@app.middleware("http")
async def security_headers(request,call_next):
    request_id=request.headers.get("x-request-id") or uid()
    token_handle=None;refresh_data=None
    public=request.url.path=="/" or request.url.path=="/app" or request.url.path.startswith("/static/") or request.url.path in {"/api/health","/api/stats","/api/auth/config","/api/auth/login","/api/auth/signup","/api/auth/logout"}
    if settings.APP_ENV=="production" and request.url.path.startswith("/api/") and request.headers.get("x-forwarded-proto",request.url.scheme)!="https":
        return JSONResponse({"detail":"HTTPS is required"},status_code=400)
    if request.url.path.startswith("/api/"):
        identity=request.client.host if request.client else "unknown";window=REQUEST_WINDOWS[identity];stamp=time.monotonic()
        while window and stamp-window[0]>60:window.popleft()
        if len(window)>=settings.RATE_LIMIT_PER_MINUTE:return JSONResponse({"detail":"Request limit reached; try again shortly"},status_code=429,headers={"Retry-After":"60"})
        window.append(stamp)
    if not hosted() and request.url.path.startswith("/api/"):
        # Local multi-user: honor the active-profile cookie (validated every request,
        # so deleting a profile instantly falls back to the default one).
        cookie_pid=request.cookies.get(PROFILE_COOKIE,"")
        if cookie_pid and cookie_pid!="default" and rows("SELECT id FROM profiles WHERE id=?",(cookie_pid,)):
            token_handle=current_user_id.set(cookie_pid)
    if hosted() and request.method in {"POST","PUT","PATCH","DELETE"} and request.url.path!="/api/system/scheduled-scan":
        origin=request.headers.get("origin","").rstrip("/");expected=settings.PUBLIC_BASE_URL.rstrip("/")
        if origin and expected and origin!=expected:return JSONResponse({"detail":"Untrusted request origin"},status_code=403)
    if hosted() and not public and request.url.path!="/api/system/scheduled-scan":
        token=request.cookies.get(settings.SESSION_COOKIE_NAME,"");refresh=request.cookies.get(settings.REFRESH_COOKIE_NAME,"")
        try:
            try:account=await authenticate(token)
            except HTTPException:
                if not refresh:raise
                refresh_data=await password_action("token?grant_type=refresh_token",{"refresh_token":refresh})
                account=await authenticate(refresh_data.get("access_token",""))
            pid=account.get("id")
            if not pid:raise HTTPException(401,"Invalid account")
            if not rows("SELECT id FROM profiles WHERE id=?",(pid,)):ensure_profile(pid,account.get("email",""))
            token_handle=current_user_id.set(pid)
            execute("UPDATE profiles SET last_active_at=?,first_warning_at=NULL,final_warning_at=NULL,deletion_scheduled_at=NULL WHERE id=?",(now(),pid))
        except HTTPException as exc:return JSONResponse({"detail":exc.detail},status_code=exc.status_code)
    try:response=await call_next(request)
    finally:
        if token_handle is not None:current_user_id.reset(token_handle)
    if refresh_data:set_session_cookies(response,refresh_data)
    if request.url.path.startswith("/static/"):
        # Static assets change between runs; always revalidate so the
        # dashboard never serves stale JavaScript after an update.
        response.headers["Cache-Control"]="no-cache"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Request-ID"]=request_id
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="no-referrer"
    # The local dashboard uses small inline event handlers; external scripts remain blocked.
    response.headers["Content-Security-Policy"]="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

@app.exception_handler(Exception)
async def unexpected_error(request:Request,exc:Exception):
    error_id=uid();LOG.exception("Unhandled request failure error_id=%s path=%s",error_id,request.url.path)
    return JSONResponse({"detail":"Unexpected server error","error_id":error_id},status_code=500,headers={"X-Error-ID":error_id})

class ProfileUpdate(BaseModel):
    full_name:str="";email:str="";current_employer:str="";current_role:str=""
    target_titles:list[str]=Field(default_factory=list);skills:list[str]=Field(default_factory=list)
    locations:list[str]=Field(default_factory=list);remote_allowed:bool=True
    excluded_roles:list[str]=Field(default_factory=list);excluded_employment_types:list[str]=Field(default_factory=list)
    country:str="India";remote_countries:list[str]=Field(default_factory=lambda:["India"])
    years_experience:float=0;relevant_experience:float=0;minimum_match_score:float=55
    work_authorization:str="India";needs_sponsorship:bool=False;notice_period_days:int=45
    expected_compensation:str="8-12 LPA";preferred_industries:list[str]=Field(default_factory=list)
    preferred_employment_types:list[str]=Field(default_factory=lambda:["full-time"])
class SourceCreate(BaseModel):name:str;provider:str;board_key:str
class SourceDetect(BaseModel):name:str;careers_url:str
class SourceToggle(BaseModel):enabled:bool
class EvidenceUpdate(BaseModel):normalized_value:str|None=None;status:str|None=None
class EvidenceBulk(BaseModel):ids:list[str];status:str
class ManualJob(BaseModel):
    title:str;company:str;location:str="";description:str="";url:HttpUrl;posted_at:str|None=None;employment_type:str=""
class ApplicationCreate(BaseModel):job_id:str;status:str="saved";notes:str=""
class ApplicationUpdate(BaseModel):
    status:str;notes:str="";recruiter_name:str="";recruiter_contact:str="";follow_up_at:str|None=None;interview_at:str|None=None
    deadline_at:str|None=None;rejection_reason:str="";salary_details:str="";offer_details:str=""
class AIRequest(BaseModel):job_id:str;instructions:str=""
class AIRouteUpdate(BaseModel):provider_ids:list[str];mode:str="automatic";allow_paid:bool=False;max_attempts:int=4
class RestoreRequest(BaseModel):path:str;confirmation:str
class ArtifactApproval(BaseModel):approved:bool
class InterviewItem(BaseModel):
    question:str;category:str="general";answer_framework:str="";star_situation:str="";star_task:str="";star_action:str="";star_result:str="";completed:bool=False;confidence:int=0;notes:str=""
class InterviewProgress(BaseModel):completed:bool
class Credentials(BaseModel):email:str;password:str=Field(min_length=8,max_length=128)
class DeleteAccount(BaseModel):confirmation:str

def no_cache():
	"""Cache-busting headers for HTML entry pages so edits show up on plain reload."""
	return {"Cache-Control":"no-store, must-revalidate", "Pragma":"no-cache", "Expires":"0"}

@app.get("/",include_in_schema=False)
def landing():return FileResponse(static/"landing"/"index.html", headers=no_cache())
@app.get("/app",include_in_schema=False)
def dashboard():return FileResponse(static/"index.html", headers=no_cache())
@app.get("/api/health")
def health():
    db_ok=rows("PRAGMA quick_check")[0].get("quick_check")=="ok"
    return {"status":"healthy" if db_ok else "degraded","version":settings.APP_VERSION,"mode":settings.DEPLOYMENT_MODE,"database":"healthy" if db_ok else "degraded","scheduler":settings.SCAN_ENABLED,"scan_hour":settings.SCAN_HOUR_LOCAL}
@app.get("/api/stats",include_in_schema=False)
def public_stats():
    """Honest, machine-local counts for the landing page. Zero on a fresh install."""
    try:
        return {
            "jobs_indexed":rows("SELECT COUNT(*) c FROM jobs")[0]["c"],
            "matches_scored":rows("SELECT COUNT(*) c FROM job_matches")[0]["c"],
            "applications":rows("SELECT COUNT(*) c FROM applications")[0]["c"],
            "auto_submissions":0,
        }
    except Exception:
        return {"jobs_indexed":0,"matches_scored":0,"applications":0,"auto_submissions":0}
@app.get("/api/ready")
def ready():
    try:rows("SELECT 1 ok");return {"ready":True}
    except Exception as exc:raise HTTPException(503,"Database is not ready") from exc
@app.get("/api/auth/config")
def auth_config():return {"hosted":hosted()}
@app.post("/api/auth/login")
async def login(credentials:Credentials,response:Response):
    data=await password_action("token?grant_type=password",credentials.model_dump());session=data.get("access_token")
    if not session:raise HTTPException(401,"Sign-in did not return a session")
    set_session_cookies(response,data)
    return {"ok":True,"user":{"id":data.get("user",{}).get("id"),"email":data.get("user",{}).get("email")}}
@app.post("/api/auth/signup")
async def signup(credentials:Credentials):
    data=await password_action("signup",credentials.model_dump());return {"ok":True,"confirmation_required":not bool(data.get("access_token"))}
@app.post("/api/auth/logout")
async def logout(request:Request,response:Response):
    await revoke(request.cookies.get(settings.SESSION_COOKIE_NAME,""));response.delete_cookie(settings.SESSION_COOKIE_NAME,path="/");response.delete_cookie(settings.REFRESH_COOKIE_NAME,path="/api/");return {"ok":True}
@app.get("/api/auth/session")
def session():return {"authenticated":True,"user_id":user_id()}
@app.delete("/api/account")
async def delete_account(item:DeleteAccount,response:Response):
    if not hosted():raise HTTPException(400,"Local data can be removed from its folder")
    if item.confirmation!="DELETE MY ACCOUNT":raise HTTPException(400,"Type DELETE MY ACCOUNT exactly")
    pid=user_id();resume_paths=[Path(x["storage_path"]) for x in rows("SELECT storage_path FROM resumes WHERE profile_id=?",(pid,))]
    with connection() as db:
        db.execute("DELETE FROM application_events WHERE application_id IN (SELECT id FROM applications WHERE profile_id=?)",(pid,))
        db.execute("DELETE FROM applications WHERE profile_id=?",(pid,));db.execute("DELETE FROM generated_artifacts WHERE owner_id=?",(pid,))
        db.execute("DELETE FROM evidence_history WHERE evidence_id IN (SELECT id FROM career_evidence WHERE profile_id=?)",(pid,))
        db.execute("DELETE FROM career_evidence WHERE profile_id=?",(pid,));db.execute("DELETE FROM resumes WHERE profile_id=?",(pid,))
        db.execute("DELETE FROM job_matches WHERE profile_id=?",(pid,));db.execute("DELETE FROM job_sources WHERE owner_id=?",(pid,))
        for table in ("notifications","scan_runs","ai_providers","ai_routes","ai_request_log","interview_prep","sync_outbox","backup_records","hidden_jobs"):
            db.execute(f"DELETE FROM {table} WHERE owner_id=?",(pid,))
        db.execute("DELETE FROM profiles WHERE id=?",(pid,))
    for path in resume_paths:
        if path.is_file() and path.parent.resolve()==settings.upload_path.resolve():path.unlink()
    await delete_auth_user(pid);response.delete_cookie(settings.SESSION_COOKIE_NAME,path="/");response.delete_cookie(settings.REFRESH_COOKIE_NAME,path="/api/")
    return {"ok":True}
@app.get("/api/profile")
def get_profile():return get_profile_data()
@app.put("/api/profile")
def update_profile(p:ProfileUpdate):
    values=(p.full_name,p.email,p.current_employer,p.current_role,json.dumps(p.target_titles),json.dumps(p.skills),json.dumps(p.locations),int(p.remote_allowed),json.dumps(p.excluded_roles),json.dumps(p.excluded_employment_types),p.country,json.dumps(p.remote_countries),p.years_experience,p.relevant_experience,p.minimum_match_score,p.work_authorization,int(p.needs_sponsorship),p.notice_period_days,p.expected_compensation,json.dumps(p.preferred_industries),json.dumps(p.preferred_employment_types),now())
    execute("UPDATE profiles SET full_name=?,email=?,current_employer=?,current_role=?,target_titles=?,skills=?,locations=?,remote_allowed=?,excluded_roles=?,excluded_employment_types=?,country=?,remote_countries=?,years_experience=?,relevant_experience=?,minimum_match_score=?,work_authorization=?,needs_sponsorship=?,notice_period_days=?,expected_compensation=?,preferred_industries=?,preferred_employment_types=?,updated_at=? WHERE id=?",values+(user_id(),))
    profile=get_profile_data();enqueue(user_id(),"profile",user_id(),"upsert",profile)
    # Full re-matching (~8k jobs) runs on the background worker; the save
    # returns instantly instead of blocking the browser for ~40 seconds.
    request_recalc(profile["id"]);return profile

class ProfileCreate(BaseModel):
    id:str="";label:str="";full_name:str="";email:str=""
class ProfileSwitch(BaseModel):profile_id:str

class LinkedInImport(BaseModel):
    url:str

@app.get("/api/linkedin/status")
def linkedin_status():
    """Whether the opt-in LinkedIn import has its provider key configured."""
    return {"configured":linkedin_import.configured()}

@app.post("/api/linkedin/import")
def linkedin_import_profile(item:LinkedInImport):
 """Fetch a LinkedIn profile (your own) via ScrapingDog as pre-fill suggestions.

 Requires SCRAPINGDOG_API_KEY in .env. Nothing is written to the profile:
 the response is a set of suggestions the user reviews before saving.
 """
 try:
  data=linkedin_import.fetch_profile(item.url)
 except RuntimeError as exc:
  raise HTTPException(502,str(exc))
 except ValueError as exc:
  raise HTTPException(422,str(exc))
 return {"fields":linkedin_import.to_profile_fields(data)}

@app.get("/api/profiles")
def list_profiles():
    """Local multi-user: every profile row is a separate user workspace."""
    if hosted():raise HTTPException(403,"Profile switching follows your hosted sign-in")
    return rows("SELECT id,full_name,email,current_role,created_at,updated_at FROM profiles ORDER BY created_at")
@app.post("/api/profiles",status_code=201)
def create_profile(item:ProfileCreate):
    if hosted():raise HTTPException(403,"Profile switching is available in local mode")
    pid=(item.id or "").strip() or ("user-"+uid()[:8])
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}",pid):raise HTTPException(422,"Profile id may only contain letters, numbers, dots, dashes and underscores")
    if rows("SELECT id FROM profiles WHERE id=?",(pid,)):raise HTTPException(409,"A profile with this id already exists")
    ensure_profile(pid,item.email or "")
    display=(item.full_name or item.label).strip()
    if display:execute("UPDATE profiles SET full_name=?,updated_at=? WHERE id=?",(display,now(),pid))
    return decode_profile(rows("SELECT * FROM profiles WHERE id=?",(pid,))[0])
@app.post("/api/session/profile")
def switch_profile(item:ProfileSwitch):
    """Activate another local profile via a long-lived cookie."""
    if hosted():raise HTTPException(403,"Profile switching follows your hosted sign-in")
    if not rows("SELECT id FROM profiles WHERE id=?",(item.profile_id,)):raise HTTPException(404,"Profile not found")
    response=JSONResponse({"ok":True,"profile_id":item.profile_id})
    response.set_cookie(PROFILE_COOKIE,item.profile_id,samesite="lax",max_age=60*60*24*365,path="/")
    return response
@app.delete("/api/profiles/{pid}")
def delete_profile(pid:str,response:Response):
    """Remove a local profile workspace and every row it owns.

    The default profile is deletable too: its data is wiped and the row reset
    to a clean workspace ("Default profile"), so the app always has a valid
    active profile. The last remaining profile cannot be deleted.
    """
    if hosted():raise HTTPException(403,"Hosted accounts use /api/account instead")
    if not rows("SELECT id FROM profiles WHERE id=?",(pid,)):raise HTTPException(404,"Profile not found")
    if not [x["id"] for x in rows("SELECT id FROM profiles WHERE id!=?",(pid,))]:raise HTTPException(400,"The last remaining profile cannot be deleted")
    resume_paths=[Path(x["storage_path"]) for x in rows("SELECT storage_path FROM resumes WHERE profile_id=?",(pid,))]
    with connection() as db:
        app_ids=[x[0] for x in db.execute("SELECT id FROM applications WHERE profile_id=?",(pid,))]
        for aid in app_ids:db.execute("DELETE FROM application_events WHERE application_id=?",(aid,))
        for table,column in (("applications","profile_id"),("job_matches","profile_id"),("career_evidence","profile_id"),("resumes","profile_id"),("job_sources","owner_id"),("notifications","owner_id"),("scan_runs","owner_id"),("generated_artifacts","owner_id"),("ai_providers","owner_id"),("ai_routes","owner_id"),("ai_request_log","owner_id"),("interview_prep","owner_id"),("story_bank","owner_id"),("fit_dossiers","owner_id"),("backup_records","owner_id"),("sync_outbox","owner_id"),("hidden_jobs","owner_id")):db.execute(f"DELETE FROM {table} WHERE {column}=?",(pid,))
        if pid=="default":
            db.execute("UPDATE profiles SET full_name='Default profile',email='',current_employer='',current_role='',target_titles='[]',skills='[]',locations='[]',remote_allowed=1,excluded_roles='[]',excluded_employment_types='[]',country='India',remote_countries=\'[\"India\"]\',years_experience=0,relevant_experience=0,minimum_match_score=55,work_authorization=\'India\',needs_sponsorship=0,notice_period_days=45,expected_compensation=\'8-12 LPA\',preferred_industries=\'[]\',preferred_employment_types=\'[\"full-time\"]\',updated_at=? WHERE id=?",(now(),pid))
        else:
            db.execute("DELETE FROM profiles WHERE id=?",(pid,))
    for path in resume_paths:
        if path.is_file() and path.parent.resolve()==settings.upload_path.resolve():path.unlink()
    if pid=="default":
        response.delete_cookie(PROFILE_COOKIE,path="/")
    else:
        response.set_cookie(PROFILE_COOKIE,"default",samesite="lax",max_age=60*60*24*365,path="/")
    return {"ok":True}

def add_evidence(rid:str,category:str,value:str,confidence=.72,section=""):
    value=value.strip()
    if value:execute("INSERT INTO career_evidence (id,profile_id,resume_id,category,normalized_value,original_text,confidence,verification_status,created_at,source_section,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(uid(),user_id(),rid,category,value,value,confidence,"unverified",now(),section,now()))

@app.post("/api/resumes",status_code=201)
async def upload_resume(file:UploadFile=File(...)):
    if file.content_type not in SUPPORTED:raise HTTPException(415,"Upload a PDF or DOCX resume")
    data=await file.read()
    if not data:raise HTTPException(400,"The uploaded file is empty")
    if len(data)>settings.MAX_UPLOAD_MB*1024*1024:raise HTTPException(413,"Resume is too large")
    if not valid_signature(data,file.content_type or ""):raise HTTPException(415,"File contents do not match the declared PDF/DOCX type")
    digest=file_hash(data);duplicate=rows("SELECT * FROM resumes WHERE profile_id=? AND file_hash=?",(user_id(),digest))
    if duplicate:return duplicate[0]
    try:text=extract_text(data,file.content_type or "")
    except Exception as exc:raise HTTPException(422,f"Document extraction failed: {exc}") from exc
    if not text:raise HTTPException(422,"No readable text found; OCR is not enabled")
    rid=uid();target=settings.upload_path/f"{rid}-{safe_filename(file.filename or 'resume')}";target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    parsed=parse_resume(text);execute("INSERT INTO resumes VALUES (?,?,?,?,?,?,?,?,?,?,?)",(rid,user_id(),file.filename or "resume",file.content_type,len(data),digest,str(target),text,json.dumps(parsed),"review_required",now()))
    targets={x.lower() for x in get_profile_data().get("target_titles",[])}
    for skill in parsed["skills"]:
        if skill.lower() not in targets:add_evidence(rid,"skill",skill,.78,"skills")
    for category in ("experience","projects","education","certifications","achievements"):
        for item in parsed.get(category,[])[:30]:add_evidence(rid,category.rstrip("s"),item.get("raw_text",str(item)),.65,category)
    enqueue(user_id(),"resume",rid,"upsert",{"id":rid,"file_name":file.filename,"file_hash":digest,"status":"review_required","created_at":now()})
    request_recalc(user_id());return {"id":rid,"file_name":file.filename,"structured":parsed}
@app.get("/api/resumes")
def list_resumes():
    data=rows("SELECT id,file_name,file_type,file_size,status,created_at,structured_json FROM resumes WHERE profile_id=? ORDER BY created_at DESC",(user_id(),))
    for item in data:item["structured"]=json.loads(item.pop("structured_json"))
    return data
@app.get("/api/evidence")
def evidence(status:str="",category:str="",q:str="",limit:int=500,offset:int=0):
    sql="SELECT e.*,r.file_name source_document FROM career_evidence e LEFT JOIN resumes r ON r.id=e.resume_id WHERE e.profile_id=?";params=[user_id()]
    if status:sql+=" AND verification_status=?";params.append(status)
    if category:sql+=" AND category=?";params.append(category)
    if q:sql+=" AND (normalized_value LIKE ? OR original_text LIKE ?)";params.extend([f"%{q}%",f"%{q}%"])
    sql+=" ORDER BY e.created_at DESC LIMIT ? OFFSET ?";params.extend([max(1,min(limit,1000)),max(0,offset)])
    return rows(sql,tuple(params))
def apply_evidence_change(eid:str,change:EvidenceUpdate):
    found=rows("SELECT * FROM career_evidence WHERE id=? AND profile_id=?",(eid,user_id()))
    if not found:raise HTTPException(404,"Evidence not found")
    old=found[0];status=change.status or old["verification_status"]
    if status not in {"verified","rejected","unverified","conflict"}:raise HTTPException(400,"Invalid status")
    value=(change.normalized_value if change.normalized_value is not None else old["normalized_value"]).strip()
    if not value:raise HTTPException(400,"Evidence value cannot be empty")
    execute("INSERT INTO evidence_history VALUES (?,?,?,?,?,?,?)",(uid(),eid,old["normalized_value"],value,old["verification_status"],status,now()))
    execute("UPDATE career_evidence SET normalized_value=?,verification_status=?,updated_at=? WHERE id=?",(value,status,now(),eid))
    update_resume_status(old["resume_id"])
    return {"ok":True,"id":eid,"status":status,"normalized_value":value}
@app.patch("/api/evidence/{eid}")
def update_evidence(eid:str,change:EvidenceUpdate,background_tasks:BackgroundTasks):
    result=apply_evidence_change(eid,change)
    enqueue(user_id(),"evidence",eid,"upsert",result)
    background_tasks.add_task(recalculate,get_profile_data())
    return result
@app.post("/api/evidence/bulk")
def bulk_evidence(change:EvidenceBulk,background_tasks:BackgroundTasks):
    if change.status not in {"verified","rejected","unverified"}:raise HTTPException(400,"Invalid status")
    for eid in change.ids:apply_evidence_change(eid,EvidenceUpdate(status=change.status))
    background_tasks.add_task(recalculate,get_profile_data())
    return {"ok":True,"updated":len(change.ids)}
def update_resume_status(rid:str):
    unresolved=rows("SELECT COUNT(*) n FROM career_evidence WHERE resume_id=? AND verification_status IN ('unverified','conflict')",(rid,))[0]["n"]
    count=rows("SELECT COUNT(*) n FROM career_evidence WHERE resume_id=?",(rid,))[0]["n"]
    execute("UPDATE resumes SET status=? WHERE id=?",("reviewed" if count and not unresolved else "partially_reviewed",rid))
@app.delete("/api/resumes/{rid}")
def delete_resume(rid:str):
    found=rows("SELECT storage_path FROM resumes WHERE id=? AND profile_id=?",(rid,user_id()))
    if not found:raise HTTPException(404,"Resume not found")
    for e in rows("SELECT id FROM career_evidence WHERE resume_id=?",(rid,)):execute("DELETE FROM evidence_history WHERE evidence_id=?",(e["id"],))
    execute("DELETE FROM career_evidence WHERE resume_id=?",(rid,));execute("DELETE FROM resumes WHERE id=?",(rid,))
    path=Path(found[0]["storage_path"])
    if path.is_file() and path.parent.resolve()==settings.upload_path.resolve():path.unlink()
    enqueue(user_id(),"resume",rid,"delete",{"id":rid});recalculate(get_profile_data());return {"ok":True}
@app.delete("/api/evidence/{eid}")
def delete_evidence(eid:str):
    found=rows("SELECT resume_id FROM career_evidence WHERE id=? AND profile_id=?",(eid,user_id()))
    if not found:raise HTTPException(404,"Evidence not found")
    execute("DELETE FROM evidence_history WHERE evidence_id=?",(eid,));execute("DELETE FROM career_evidence WHERE id=? AND profile_id=?",(eid,user_id()))
    update_resume_status(found[0]["resume_id"]);enqueue(user_id(),"evidence",eid,"delete",{"id":eid});recalculate(get_profile_data());return {"ok":True}

@app.post("/api/sources/seed")
def seed_sources():
    added=0
    for name,provider,board,default_enabled in SEED_SOURCES:
        if not rows("SELECT id FROM job_sources WHERE owner_id=? AND provider=? AND board_key=?",(user_id(),provider,board)):
            enabled=default_enabled and (provider=="arbeitnow" or provider in {"remotive","remoteok","jobicy","himalayas"} or provider=="adzuna" and bool(settings.ADZUNA_APP_ID) or provider=="jooble" and bool(settings.JOOBLE_API_KEY))
            execute("INSERT INTO job_sources (id,name,provider,board_key,enabled,created_at,owner_id) VALUES (?,?,?,?,?,?,?)",(uid(),name,provider,board,int(enabled),now(),user_id()));added+=1
    return {"added":added}
@app.post("/api/sources",status_code=201)
def add_source(source:SourceCreate):
    if source.provider not in PROVIDERS:raise HTTPException(400,"Unsupported source provider")
    try:execute("INSERT INTO job_sources (id,name,provider,board_key,enabled,created_at,owner_id) VALUES (?,?,?,?,?,?,?)",(uid(),source.name.strip(),source.provider,source.board_key.strip(),1,now(),user_id()))
    except Exception as exc:raise HTTPException(409,"Source already exists") from exc
    return source
@app.get("/api/sources")
def list_sources():return rows("SELECT * FROM job_sources WHERE owner_id=? ORDER BY enabled DESC,name",(user_id(),))
@app.patch("/api/sources/{sid}")
def toggle_source(sid:str,change:SourceToggle):execute("UPDATE job_sources SET enabled=? WHERE id=? AND owner_id=?",(int(change.enabled),sid,user_id()));return {"ok":True}
@app.delete("/api/sources/{sid}")
def delete_source(sid:str):execute("DELETE FROM job_sources WHERE id=? AND owner_id=?",(sid,user_id()));return {"ok":True}
@app.post("/api/sources/detect")
def detect_source(item:SourceDetect):
    url=urlparse(item.careers_url)
    if url.scheme!="https":raise HTTPException(400,"Careers URL must use HTTPS")
    parts=[x for x in url.path.split("/") if x];host=(url.hostname or "").lower();provider="";board=""
    if host=="jobs.ashbyhq.com":provider="ashby";board=parts[0] if parts else ""
    elif host in {"jobs.lever.co","jobs.eu.lever.co"}:provider="lever";board=parts[0] if parts else ""
    elif host in {"boards.greenhouse.io","job-boards.greenhouse.io","job-boards.eu.greenhouse.io"}:provider="greenhouse";board=parts[0] if parts else ""
    elif host=="jobs.smartrecruiters.com":provider="smartrecruiters";board=parts[0] if parts else ""
    elif host.endswith(".recruitee.com"):provider="recruitee";board=host.split(".")[0]
    if not provider or not re.fullmatch(r"[A-Za-z0-9._-]+",board):raise HTTPException(422,"Supported ATS not detected. Import the job manually instead.")
    return {"name":item.name,"provider":provider,"board_key":board,"careers_url":item.careers_url}

@app.post("/api/jobs/scan")
async def scan_jobs():return await scan(get_profile_data(),"manual")
@app.post("/api/sources/{sid}/retry")
async def retry_source(sid:str):
    source=rows("SELECT * FROM job_sources WHERE id=? AND owner_id=?",(sid,user_id()))
    if not source:raise HTTPException(404,"Source not found")
    execute("UPDATE job_sources SET enabled=1,cooldown_until=NULL WHERE id=?",(sid,))
    return await scan(get_profile_data(),"source_retry",sid)
@app.post("/api/system/scheduled-scan",include_in_schema=False)
async def scheduled_scan(x_cron_secret:str=Header(default="")):
    if not settings.CRON_SECRET or x_cron_secret!=settings.CRON_SECRET:
        raise HTTPException(401,"Invalid scheduler credential")
    results=[]
    for profile in rows("SELECT * FROM profiles WHERE id!='default'" if hosted() else "SELECT * FROM profiles"):
        results.append(await scan(decode_profile(profile),"external_scheduler"))
    return {"users_scanned":len(results),"results":results}
@app.post("/api/jobs/manual",status_code=201)
def manual_job(item:ManualJob):
    url=str(item.url);sid=key("manual",url);canonical=canonical_key(item.company,item.title,item.location)
    if rows("SELECT id FROM jobs WHERE source_key=?",(sid,)):raise HTTPException(409,"Job URL is already saved")
    execute("INSERT INTO jobs (id,source_key,provider,source_name,title,company,location,description,url,posted_at,first_seen_at,date_semantics,employment_type,is_active,raw_json,last_seen_at,liveness_status,canonical_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(uid(),sid,"manual","Manual import",item.title,item.company,item.location,item.description,url,item.posted_at,now(),"user_supplied",item.employment_type,1,"{}",now(),"unknown",canonical))
    request_recalc(user_id());return {"ok":True}
@app.get("/api/jobs")
def list_jobs(hours:int=48,provider:str="",classification:str="qualified",company:str="",q:str="",strict_date:bool=True,minimum_score:float=0,limit:int=60,offset:int=0):
    profile=get_profile_data();threshold=max(minimum_score,0);cutoff=(datetime.now(timezone.utc)-timedelta(hours=max(1,hours))).isoformat() if hours>=0 else ""
    where="FROM jobs j JOIN job_matches m ON m.job_id=j.id AND m.profile_id=? WHERE j.is_active=1 AND m.score>=? AND NOT EXISTS (SELECT 1 FROM hidden_jobs h WHERE h.owner_id=? AND h.job_id=j.id)";params=[user_id(),threshold,user_id()]
    if hours>=0:
        if strict_date:where+=" AND j.posted_at IS NOT NULL AND j.posted_at>=?";params.append(cutoff)
        else:where+=" AND COALESCE(j.posted_at,j.first_seen_at)>=?";params.append(cutoff)
    if provider:where+=" AND j.provider=?";params.append(provider)
    if classification and classification!="all":where+=" AND m.classification=?";params.append(classification)
    if company:where+=" AND j.company LIKE ?";params.append(f"%{company}%")
    if q:where+=" AND (j.title LIKE ? OR j.description LIKE ?)";params.extend([f"%{q}%",f"%{q}%"])
    total=rows(f"SELECT count(*) AS n {where}",tuple(params))[0]["n"]
    data=rows(f"SELECT j.*,m.score,m.matched_skills,m.missing_skills,m.reasons,m.classification,m.components,m.blockers,m.matcher_version {where} ORDER BY m.score DESC,j.posted_at DESC LIMIT ? OFFSET ?",tuple(params+[max(1,min(limit,500)),max(0,offset)]))
    for x in data:
        for f in ("matched_skills","missing_skills","reasons","blockers"):x[f]=json.loads(x.get(f) or "[]")
        x["components"]=json.loads(x.get("components") or "{}")
    return {"total":total,"limit":limit,"offset":offset,"items":data}
@app.delete("/api/jobs/{job_id}")
def hide_job(job_id:str):
    if not rows("SELECT id FROM jobs WHERE id=?",(job_id,)):raise HTTPException(404,"Job not found")
    execute("INSERT OR REPLACE INTO hidden_jobs VALUES (?,?,?)",(user_id(),job_id,now()));return {"ok":True}

ALLOWED_STATUSES={"discovered","evaluated","ineligible","rejected","shortlisted","saved","preparing","ready_to_apply","applied","recruiter_contacted","assessment","interview","on_hold","withdrawn","offer","accepted"}
@app.post("/api/applications",status_code=201)
def save_application(item:ApplicationCreate):
    if item.status not in ALLOWED_STATUSES:raise HTTPException(400,"Invalid status")
    ts=now();old=rows("SELECT id FROM applications WHERE profile_id=? AND job_id=?",(user_id(),item.job_id))
    if old:execute("UPDATE applications SET status=?,notes=?,updated_at=? WHERE id=?",(item.status,item.notes,ts,old[0]["id"]));aid=old[0]["id"]
    else:aid=uid();execute("INSERT INTO applications (id,profile_id,job_id,status,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",(aid,user_id(),item.job_id,item.status,item.notes,ts,ts));execute("INSERT INTO application_events VALUES (?,?,?,?,?,?)",(uid(),aid,None,item.status,item.notes,ts))
    result={"id":aid,**item.model_dump()};enqueue(user_id(),"application",aid,"upsert",result);return result
@app.get("/api/applications")
def applications(include_archived:bool=False):
    sql="SELECT a.*,j.title,j.company,j.location,j.url,j.provider,m.score,m.matcher_version FROM applications a JOIN jobs j ON j.id=a.job_id LEFT JOIN job_matches m ON m.job_id=j.id AND m.profile_id=? WHERE a.profile_id=?";params=[user_id(),user_id()]
    if not include_archived:sql+=" AND a.archived=0"
    return rows(sql+" ORDER BY a.updated_at DESC",tuple(params))
@app.patch("/api/applications/{aid}")
def update_application(aid:str,change:ApplicationUpdate):
    if change.status not in ALLOWED_STATUSES:raise HTTPException(400,"Invalid status")
    old=rows("SELECT * FROM applications WHERE id=? AND profile_id=?",(aid,user_id()))
    if not old:raise HTTPException(404,"Application not found")
    execute("UPDATE applications SET status=?,notes=?,recruiter_name=?,recruiter_contact=?,follow_up_at=?,interview_at=?,deadline_at=?,rejection_reason=?,salary_details=?,offer_details=?,updated_at=? WHERE id=? AND profile_id=?",(change.status,change.notes,change.recruiter_name,change.recruiter_contact,change.follow_up_at,change.interview_at,change.deadline_at,change.rejection_reason,change.salary_details,change.offer_details,now(),aid,user_id()))
    execute("INSERT INTO application_events VALUES (?,?,?,?,?,?)",(uid(),aid,old[0]["status"],change.status,change.notes,now()));enqueue(user_id(),"application",aid,"upsert",change.model_dump());return {"ok":True}
@app.get("/api/applications/{aid}/history")
def application_history(aid:str):
    if not rows("SELECT id FROM applications WHERE id=? AND profile_id=?",(aid,user_id())):raise HTTPException(404,"Application not found")
    return rows("SELECT * FROM application_events WHERE application_id=? ORDER BY created_at DESC",(aid,))
@app.post("/api/applications/{aid}/archive")
def archive_application(aid:str):execute("UPDATE applications SET archived=1,updated_at=? WHERE id=? AND profile_id=?",(now(),aid,user_id()));return {"ok":True}
@app.delete("/api/applications/{aid}")
def delete_application(aid:str):
    owned=rows("SELECT id FROM applications WHERE id=? AND profile_id=?",(aid,user_id()))
    if not owned:raise HTTPException(404,"Application not found")
    execute("DELETE FROM application_events WHERE application_id=?",(aid,));execute("DELETE FROM applications WHERE id=? AND profile_id=?",(aid,user_id()));enqueue(user_id(),"application",aid,"delete",{"id":aid});return {"ok":True}

@app.get("/api/notifications")
def notifications():return rows("SELECT * FROM notifications WHERE owner_id=? ORDER BY created_at DESC LIMIT 50",(user_id(),))
@app.post("/api/notifications/{nid}/read")
def read_notification(nid:str):execute("UPDATE notifications SET is_read=1 WHERE id=? AND owner_id=?",(nid,user_id()));return {"ok":True}
@app.get("/api/insights")
def insights():
    return {"providers":rows("SELECT j.provider,COUNT(*) jobs FROM jobs j JOIN job_matches m ON m.job_id=j.id WHERE m.profile_id=? GROUP BY j.provider ORDER BY jobs DESC",(user_id(),)),"pipeline":rows("SELECT status,COUNT(*) count FROM applications WHERE profile_id=? AND archived=0 GROUP BY status",(user_id(),)),"scans":rows("SELECT * FROM scan_runs WHERE owner_id=? ORDER BY started_at DESC LIMIT 10",(user_id(),))}
@app.post("/api/backup")
def create_backup():
    if hosted():raise HTTPException(403,"Server-wide backup is available only to the hosting administrator")
    path=backup();check=verify_backup(path);execute("INSERT INTO backup_records VALUES (?,?,?,?,?,?,?)",(uid(),user_id(),path,check["size_bytes"],check["checksum"],"verified" if check["valid"] else "invalid",now()));return check
@app.get("/api/backups")
def backups():return list_backups()
@app.post("/api/backups/restore")
def restore(item:RestoreRequest):
    if hosted():raise HTTPException(403,"Restore is available only in local mode")
    if item.confirmation!="RESTORE BACKUP":raise HTTPException(400,"Type RESTORE BACKUP exactly")
    try:restore_backup(item.path)
    except (ValueError,FileNotFoundError) as exc:raise HTTPException(400,str(exc)) from exc
    return {"ok":True}
@app.get("/api/storage")
def storage():return storage_usage()|{"sync":sync_status(user_id())}
@app.post("/api/storage/cleanup")
def cleanup_storage():
    referenced={Path(x["storage_path"]).resolve() for x in rows("SELECT storage_path FROM resumes")}
    removed=0
    for path in settings.upload_path.glob("*"):
        if path.is_file() and path.resolve() not in referenced:path.unlink();removed+=1
    return {"removed":removed}
@app.get("/api/sync")
def cloud_sync_status():return sync_status(user_id())
@app.post("/api/sync")
def run_cloud_sync():return sync_pending(user_id())
@app.get("/api/export")
def export_data():
    payload={"version":settings.APP_VERSION,"exported_at":now(),"profile":get_profile_data(),"resumes":list_resumes(),"evidence":evidence(),"sources":list_sources(),"applications":applications(True)}
    target=Path("data/exports")/f"karna-os-export-{user_id()[:8]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json";target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return FileResponse(target,filename=target.name,media_type="application/json")

async def ai_generate(kind:str,request:AIRequest):
    gateway=AIRouter(user_id())
    if not gateway.enabled:raise HTTPException(503,"AI is disabled. Configure an authorized API provider or local Ollama in .env")
    jobs=rows("SELECT j.* FROM jobs j JOIN job_matches m ON m.job_id=j.id WHERE j.id=? AND m.profile_id=?",(request.job_id,user_id()));resumes=rows("SELECT extracted_text FROM resumes WHERE profile_id=? ORDER BY created_at DESC LIMIT 1",(user_id(),))
    if not jobs:raise HTTPException(404,"Job not found")
    verified=rows("SELECT category,normalized_value,original_text FROM career_evidence WHERE profile_id=? AND verification_status='verified'",(user_id(),))
    templates={
      "tailor":"Create an ATS-friendly tailored resume in Markdown. Preserve every employer, date, education item and metric exactly. Do not add unsupported claims.",
      "cover-letter":"Draft a concise, human cover letter grounded only in verified evidence. Do not invent experience.",
      "interview-prep":"Create technical, behavioural, and project questions, answer frameworks, likely weak areas, and a two-day study plan.",
      "recruiter-review":"Act as the first screening and hiring review. Return: verdict (strong fit, possible fit, or weak fit); mandatory requirement check; preferred requirement check; evidence-backed strengths; gaps and risks; likely recruiter objections; exact resume improvements; screening questions with truthful answer guidance; and the three highest-value next actions. Do not turn the verdict into a hiring probability.",
      "application-email":"Draft a formal application email to a recruiter or hiring manager. Return: a subject line; a 120-180 word body with source-grounded fit points (no invented claims); an attachment checklist; and a sign-off block using the candidate's name and contact details from the profile when available. This is a draft only; the user will copy it into their own email client.",
    }
    profile=get_profile_data()
    prompt=f"TASK: {templates[kind]}\n{recruiter_context(jobs[0],profile,verified)}\nJOB: {json.dumps(jobs[0])}\nSOURCE RESUME: {resumes[0]['extracted_text'] if resumes else 'Not supplied'}\nUSER INSTRUCTIONS: {request.instructions}"
    try:result=await gateway.chat(kind,[{"role":"system","content":senior_recruiter_system_prompt(jobs[0],profile)},{"role":"user","content":prompt}])
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc
    artifact_id=uid();execute("INSERT INTO generated_artifacts (id,job_id,kind,content,model,created_at,owner_id,status,metadata) VALUES (?,?,?,?,?,?,?,?,?)",(artifact_id,request.job_id,kind,result["content"],result["model"],now(),user_id(),"draft",json.dumps({"provider":result["provider"],"attempts":result["attempts"],"fallback_reason":result["fallback_reason"]})))
    return {"artifact_id":artifact_id,**result}
@app.post("/api/ai/tailor")
async def tailor_resume(request:AIRequest):return await ai_generate("tailor",request)
@app.post("/api/ai/cover-letter")
async def cover_letter(request:AIRequest):return await ai_generate("cover-letter",request)
@app.post("/api/ai/interview-prep")
async def interview_prep(request:AIRequest):return await ai_generate("interview-prep",request)
@app.post("/api/ai/recruiter-review")
async def recruiter_review(request:AIRequest):return await ai_generate("recruiter-review",request)
@app.post("/api/ai/application-email")
async def application_email(request:AIRequest):return await ai_generate("application-email",request)
@app.get("/api/ai/router")
def ai_router_status():return router_status(user_id())
@app.put("/api/ai/routes/{task}")
def update_ai_route(task:str,change:AIRouteUpdate):
    found=rows("SELECT id FROM ai_routes WHERE owner_id=? AND task=?",(user_id(),task))
    if not found:raise HTTPException(404,"AI task route not found")
    valid={x["id"] for x in rows("SELECT id FROM ai_providers WHERE owner_id=?",(user_id(),))}
    if any(x not in valid for x in change.provider_ids):raise HTTPException(400,"Route contains an unknown provider")
    execute("UPDATE ai_routes SET provider_ids=?,mode=?,allow_paid=?,max_attempts=?,updated_at=? WHERE id=?",(json.dumps(change.provider_ids),change.mode,int(change.allow_paid),max(1,min(change.max_attempts,10)),now(),found[0]["id"]));return {"ok":True}
@app.get("/api/artifacts")
def artifacts(job_id:str=""):
    sql="SELECT * FROM generated_artifacts WHERE owner_id=?";params=[user_id()]
    if job_id:sql+=" AND job_id=?";params.append(job_id)
    data=rows(sql+" ORDER BY created_at DESC",tuple(params))
    for x in data:x["metadata"]=json.loads(x.get("metadata") or "{}")
    return data
@app.post("/api/artifacts/{artifact_id}/approval")
def approve_artifact(artifact_id:str,item:ArtifactApproval):
    found=rows("SELECT id FROM generated_artifacts WHERE id=? AND owner_id=?",(artifact_id,user_id()))
    if not found:raise HTTPException(404,"Artifact not found")
    execute("UPDATE generated_artifacts SET status=?,approved_at=? WHERE id=?",("approved" if item.approved else "rejected",now() if item.approved else None,artifact_id));return {"ok":True}
@app.get("/api/artifacts/{artifact_id}/compare")
def compare_artifact(artifact_id:str):
    artifact=rows("SELECT * FROM generated_artifacts WHERE id=? AND owner_id=?",(artifact_id,user_id()))
    if not artifact:raise HTTPException(404,"Artifact not found")
    source=rows("SELECT extracted_text FROM resumes WHERE profile_id=? ORDER BY created_at DESC LIMIT 1",(user_id(),))
    before=(source[0]["extracted_text"] if source else "").splitlines();after=artifact[0]["content"].splitlines()
    return {"diff":"\n".join(difflib.unified_diff(before,after,fromfile="original",tofile="tailored",lineterm=""))}
@app.get("/api/artifacts/{artifact_id}/export")
def export_artifact(artifact_id:str,format:str=Query(pattern="^(pdf|docx)$")):
    found=rows("SELECT * FROM generated_artifacts WHERE id=? AND owner_id=?",(artifact_id,user_id()))
    if not found:raise HTTPException(404,"Artifact not found")
    if found[0].get("status")!="approved":raise HTTPException(409,"Approve the document before export")
    data=to_pdf("Karna OS approved document",found[0]["content"]) if format=="pdf" else to_docx("Karna OS approved document",found[0]["content"])
    mime="application/pdf" if format=="pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return StreamingResponse(io.BytesIO(data),media_type=mime,headers={"Content-Disposition":f'attachment; filename="karna-{found[0]["kind"]}.{format}"'})
@app.delete("/api/artifacts/{artifact_id}")
def delete_artifact(artifact_id:str):execute("DELETE FROM generated_artifacts WHERE id=? AND owner_id=?",(artifact_id,user_id()));return {"ok":True}
@app.get("/api/interview/{job_id}")
def interview_items(job_id:str):return rows("SELECT * FROM interview_prep WHERE owner_id=? AND job_id=? ORDER BY completed,created_at",(user_id(),job_id))
@app.post("/api/interview/{job_id}",status_code=201)
def create_interview_item(job_id:str,item:InterviewItem):
    if not rows("SELECT id FROM jobs WHERE id=?",(job_id,)):raise HTTPException(404,"Job not found")
    iid=uid();stamp=now();execute("INSERT INTO interview_prep VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(iid,user_id(),job_id,item.question,item.category,item.answer_framework,item.star_situation,item.star_task,item.star_action,item.star_result,int(item.completed),max(0,min(item.confidence,5)),item.notes,stamp,stamp));return {"id":iid}
@app.put("/api/interview/items/{iid}")
def update_interview_item(iid:str,item:InterviewItem):
    execute("UPDATE interview_prep SET question=?,category=?,answer_framework=?,star_situation=?,star_task=?,star_action=?,star_result=?,completed=?,confidence=?,notes=?,updated_at=? WHERE id=? AND owner_id=?",(item.question,item.category,item.answer_framework,item.star_situation,item.star_task,item.star_action,item.star_result,int(item.completed),max(0,min(item.confidence,5)),item.notes,now(),iid,user_id()));return {"ok":True}
@app.patch("/api/interview/items/{iid}/progress")
def update_interview_progress(iid:str,item:InterviewProgress):
    execute("UPDATE interview_prep SET completed=?,updated_at=? WHERE id=? AND owner_id=?",(int(item.completed),now(),iid,user_id()));return {"ok":True}
@app.delete("/api/interview/items/{iid}")
def delete_interview_item(iid:str):execute("DELETE FROM interview_prep WHERE id=? AND owner_id=?",(iid,user_id()));return {"ok":True}

# ── Fit Dossier: deep per-job evaluation ─────────────────────────────
@app.get("/api/dossier/{job_id}")
def get_dossier(job_id:str):
    latest=rows("SELECT * FROM fit_dossiers WHERE owner_id=? AND job_id=? ORDER BY created_at DESC LIMIT 1",(user_id(),job_id))
    if not latest:return {"dossier":None}
    d=latest[0]
    return {"dossier":{"id":d["id"],"global_score":d["global_score"],"verdict":d["verdict"],"dimensions":json.loads(d["dimensions"]),"requirements":json.loads(d["requirement_weights"]),"legitimacy":json.loads(d["legitimacy"]),"interview_focus":json.loads(d["interview_focus"]),"recommended_actions":json.loads(d["recommended_actions"]),"model":d["model"],"source":d["source"],"created_at":d["created_at"]}}

@app.post("/api/dossier/{job_id}",status_code=201)
async def generate_dossier(job_id:str):
    """Holistic deep evaluation. AI when configured; honest deterministic fallback otherwise."""
    jobrows=rows("SELECT j.* FROM jobs j JOIN job_matches m ON m.job_id=j.id WHERE j.id=? AND m.profile_id=?",(job_id,user_id()))
    if not jobrows:
        jobrows=rows("SELECT * FROM jobs WHERE id=?",(job_id,))
    if not jobrows:raise HTTPException(404,"Job not found")
    job=dict(jobrows[0]);profile=get_profile_data()
    matches=rows("SELECT * FROM job_matches WHERE profile_id=? AND job_id=? ORDER BY created_at DESC LIMIT 1",(user_id(),job_id))
    match=dict(matches[0]) if matches else None
    if match:
        for field in ("matched_skills","missing_skills","reasons","components","blockers"):
            try:match[field]=json.loads(match.get(field) or "[]")
            except json.JSONDecodeError:match[field]=[]
    verified=rows("SELECT category,normalized_value,original_text FROM career_evidence WHERE profile_id=? AND verification_status='verified'",(user_id(),))
    stories=rows("SELECT title,category,situation,task,action,result FROM story_bank WHERE owner_id=? AND status='ready' ORDER BY updated_at DESC",(user_id(),))
    model="";parsed=None
    try:
        gateway=AIRouter(user_id())
        if gateway.enabled:
            result=await gateway.chat("dossier",[{"role":"system","content":"Return only the JSON object specified by the user."},{"role":"user","content":dossier_prompt(job,profile,verified,stories,match)}])
            parsed=parse_dossier_json(result["content"])
            if parsed:model=result["model"]
    except RuntimeError:parsed=None
    if not parsed:
        parsed=basic_dossier(job,profile,match);model=model or ""
    legitimacy=legitimacy_check(job);source="ai" if model else "basic"
    did=uid();stamp=now()
    execute("INSERT INTO fit_dossiers (id,owner_id,job_id,global_score,verdict,dimensions,requirement_weights,legitimacy,interview_focus,recommended_actions,model,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did,user_id(),job_id,parsed["global_score"],parsed["verdict"],json.dumps(parsed["dimensions"]),json.dumps(parsed["requirements"]),json.dumps(legitimacy),json.dumps(parsed["interview_focus"]),json.dumps(parsed["recommended_actions"]),model,source,stamp))
    return {"dossier":{"id":did,"global_score":parsed["global_score"],"verdict":parsed["verdict"],"dimensions":parsed["dimensions"],"requirements":parsed["requirements"],"legitimacy":legitimacy,"interview_focus":parsed["interview_focus"],"recommended_actions":parsed["recommended_actions"],"model":model,"source":source,"created_at":stamp}}

# ── Story Bank: master STAR stories reused across every evaluation ───
@app.get("/api/stories")
def list_stories():
    items=rows("SELECT * FROM story_bank WHERE owner_id=? ORDER BY updated_at DESC",(user_id(),))
    for s in items:s["tags"]=json.loads(s.get("tags") or "[]")
    return items

class StoryItem(BaseModel):
    title:str;category:str="general";situation:str="";task:str="";action:str="";result:str="";reflection:str="";tags:list[str]=[];status:str="draft"

@app.post("/api/stories",status_code=201)
def create_story(item:StoryItem):
    sid=uid();stamp=now()
    execute("INSERT INTO story_bank (id,owner_id,title,category,situation,task,action,result,reflection,tags,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid,user_id(),item.title.strip()[:120],item.category.strip()[:40] or "general",item.situation.strip(),item.task.strip(),item.action.strip(),item.result.strip(),item.reflection.strip(),json.dumps([t.strip()[:30] for t in item.tags if t.strip()][:8]),"ready" if item.status=="ready" else "draft",stamp,stamp))
    return {"id":sid}

@app.put("/api/stories/{sid}")
def update_story(sid:str,item:StoryItem):
    if not rows("SELECT id FROM story_bank WHERE id=? AND owner_id=?",(sid,user_id())):raise HTTPException(404,"Story not found")
    execute("UPDATE story_bank SET title=?,category=?,situation=?,task=?,action=?,result=?,reflection=?,tags=?,status=?,updated_at=? WHERE id=? AND owner_id=?",
            (item.title.strip()[:120],item.category.strip()[:40] or "general",item.situation.strip(),item.task.strip(),item.action.strip(),item.result.strip(),item.reflection.strip(),json.dumps([t.strip()[:30] for t in item.tags if t.strip()][:8]),"ready" if item.status=="ready" else "draft",now(),sid,user_id()))
    return {"ok":True}

@app.delete("/api/stories/{sid}")
def delete_story(sid:str):execute("DELETE FROM story_bank WHERE id=? AND owner_id=?",(sid,user_id()));return {"ok":True}

# ── Pipeline Intel: funnel, follow-ups, ghost signals ───────────────
@app.get("/api/pipeline/intel")
def pipeline_intel():
    pid=user_id()
    funnel=rows("SELECT status,COUNT(*) count,MAX(updated_at) last_move FROM applications WHERE profile_id=? AND archived=0 GROUP BY status ORDER BY count DESC",(pid,))
    total=sum(int(x["count"]) for x in funnel) or 0
    reached={x["status"]:int(x["count"]) for x in funnel}
    def stage(*names:str):return sum(reached.get(n,0) for n in names)
    # Funnel conversion: the share of tracked applications that ever got a human response.
    responses=stage("screening","interview","offer","accepted")
    conversion=round(100*responses/total,1) if total else 0.0
    overdue=[dict(x) for x in rows("""SELECT a.id,a.job_id,a.status,a.follow_up_at,a.notes,j.title,j.company FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.profile_id=? AND a.archived=0 AND a.follow_up_at IS NOT NULL AND a.follow_up_at<=? AND a.status NOT IN ('rejected','withdrawn','accepted') ORDER BY a.follow_up_at LIMIT 12""",(pid,now()))]
    suggestions=rows("""SELECT a.id,j.title,j.company,a.status,a.updated_at FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.profile_id=? AND a.archived=0 AND a.status='applied' AND a.follow_up_at IS NULL AND a.updated_at<=datetime('now','-7 days') ORDER BY a.updated_at LIMIT 8""",(pid,))
    ghosts=[dict(x) for x in rows("SELECT id,title,company,repost_count,duplicate_count,posted_at FROM jobs WHERE id IN (SELECT job_id FROM applications WHERE profile_id=? AND archived=0) AND (repost_count>=2 OR duplicate_count>=3) LIMIT 8",(pid,))]
    interview_stats=rows("SELECT COUNT(*) total,SUM(completed) done,ROUND(AVG(confidence),1) avg_conf FROM interview_prep WHERE owner_id=?",(pid,))
    stories_count=int(rows("SELECT COUNT(*) c FROM story_bank WHERE owner_id=? AND status='ready'",(pid,))[0]["c"])
    dossiers=rows("SELECT verdict,COUNT(*) count FROM fit_dossiers WHERE owner_id=? GROUP BY verdict",(pid,))
    return {"funnel":funnel,"total":total,"response_rate":conversion,"overdue_followups":overdue,"followup_suggestions":suggestions,"ghost_signals":ghosts,"interview":{"total":int(interview_stats[0]["total"] or 0),"completed":int(interview_stats[0]["done"] or 0),"avg_confidence":float(interview_stats[0]["avg_conf"] or 0)},"stories_ready":stories_count,"dossier_verdicts":dossiers}

@app.post("/api/applications/{aid}/follow-up")
def set_follow_up(aid:str,body:dict|None=None):
    """Set (or snooze) the follow-up reminder without touching any other field."""
    found=rows("SELECT id,status FROM applications WHERE id=? AND profile_id=?",(aid,user_id()))
    if not found:raise HTTPException(404,"Application not found")
    when=((body or {}).get("follow_up_at") or "").strip()
    if not when:
        from datetime import timedelta as _td
        when=(datetime.now(timezone.utc)+_td(days=7)).isoformat()
    execute("UPDATE applications SET follow_up_at=?,updated_at=? WHERE id=? AND profile_id=?",(when,now(),aid,user_id()))
    return {"ok":True,"follow_up_at":when}
