"""Approved job-source connectors.

Only documented JSON APIs are called. Connectors never submit applications,
authenticate to job portals, solve CAPTCHAs, or scrape restricted HTML.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
import hashlib
import re
from typing import Any

import httpx

from backend.core.config_new import settings


@dataclass
class Job:
    source_key: str
    provider: str
    source_name: str
    title: str
    company: str
    location: str
    description: str
    url: str
    posted_at: str | None
    date_semantics: str
    employment_type: str = ""
    raw_json: dict | None = None

    def dict(self): return asdict(self)


def key(provider: str, value: str) -> str:
    return hashlib.sha256(f"{provider}:{value}".encode()).hexdigest()


def fingerprint(company: str, title: str, location: str, description: str) -> str:
    normal = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    core = "|".join((normal(company), normal(title), normal(location), normal(description)[:500]))
    return hashlib.sha256(core.encode()).hexdigest()

def canonical_key(company: str, title: str, location: str) -> str:
    """Cross-provider vacancy identity; intentionally excludes provider and description."""
    normal=lambda s:re.sub(r"\b(the|inc|llc|ltd|limited|private|pvt|corporation|corp)\b|[^a-z0-9]+"," ",(s or "").lower()).strip()
    title_clean=re.sub(r"\b(jr|sr|ii|iii)\b","",normal(title))
    location_clean=re.sub(r"\b(remote|hybrid|on site|onsite)\b","",normal(location))
    return hashlib.sha256("|".join((normal(company),title_clean,location_clean)).encode()).hexdigest()


def clean_html(value: str) -> str:
    value = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value or "", flags=re.I | re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def iso(value: Any) -> str | None:
    if value in (None, ""): return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def valid_slug(board: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", board or ""):
        raise ValueError("Invalid ATS board identifier")
    return board


async def greenhouse(board: str, company: str, _profile: dict) -> list[Job]:
    board = valid_slug(board)
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        data = (await client.get(url)).raise_for_status().json()
    return [Job(key("greenhouse", str(j["id"])), "greenhouse", board, j.get("title",""), company,
        (j.get("location") or {}).get("name",""), clean_html(j.get("content","")), j.get("absolute_url",""),
        iso(j.get("first_published") or j.get("updated_at")), "posted" if j.get("first_published") else "updated",
        raw_json=j) for j in data.get("jobs",[]) if j.get("absolute_url")]


async def lever(board: str, company: str, _profile: dict) -> list[Job]:
    board = valid_slug(board)
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        data = (await client.get(url)).raise_for_status().json()
    out=[]
    for j in data:
        cats=j.get("categories") or {}; job_url=j.get("hostedUrl","")
        if job_url: out.append(Job(key("lever",j.get("id",job_url)),"lever",board,j.get("text",""),company,
            cats.get("location",""),clean_html(j.get("descriptionPlain") or j.get("description","")),job_url,
            iso(j.get("createdAt")),"posted",cats.get("commitment",""),j))
    return out


async def ashby(board: str, company: str, _profile: dict) -> list[Job]:
    board=valid_slug(board)
    url=f"https://api.ashbyhq.com/posting-api/job-board/{board}"
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        data=(await client.get(url)).raise_for_status().json()
    return [Job(key("ashby",j.get("jobUrl","")),"ashby",board,j.get("title",""),company,j.get("location",""),
        clean_html(j.get("descriptionPlain","")),j.get("jobUrl",""),iso(j.get("publishedAt")),"posted",
        j.get("employmentType",""),j) for j in data.get("jobs",[]) if j.get("jobUrl")]


async def smartrecruiters(board: str, company: str, _profile: dict) -> list[Job]:
    board=valid_slug(board)
    url=f"https://api.smartrecruiters.com/v1/companies/{board}/postings?limit=100"
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        data=(await client.get(url)).raise_for_status().json()
    out=[]
    for j in data.get("content",[]):
        loc=j.get("location") or {}; jid=str(j.get("id","")); job_url=f"https://jobs.smartrecruiters.com/{board}/{jid}"
        out.append(Job(key("smartrecruiters",jid),"smartrecruiters",board,j.get("name",""),company,
            ", ".join(x for x in (loc.get("city"),loc.get("region"),loc.get("country")) if x),"",job_url,
            iso(j.get("releasedDate")),"posted",(j.get("typeOfEmployment") or {}).get("label",""),j))
    return out


async def recruitee(board: str, company: str, _profile: dict) -> list[Job]:
    board=valid_slug(board)
    url=f"https://{board}.recruitee.com/api/offers/"
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        data=(await client.get(url)).raise_for_status().json()
    out=[]
    for j in data.get("offers",[]):
        job_url=j.get("careers_url") or j.get("url",""); jid=str(j.get("id",job_url))
        out.append(Job(key("recruitee",jid),"recruitee",board,j.get("title",""),company,
            j.get("location",""),clean_html(j.get("description","")),job_url,
            iso(j.get("published_at") or j.get("created_at")),"posted",j.get("employment_type",""),j))
    return [x for x in out if x.url]


async def arbeitnow(_board: str, _company: str, _profile: dict) -> list[Job]:
    out=[]
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for page in range(1,4):
            data=(await client.get("https://www.arbeitnow.com/api/job-board-api",params={"page":page})).raise_for_status().json()
            for j in data.get("data",[]):
                jid=str(j.get("slug") or j.get("url")); out.append(Job(key("arbeitnow",jid),"arbeitnow","global",
                    j.get("title",""),j.get("company_name",""),j.get("location",""),clean_html(j.get("description","")),
                    j.get("url",""),iso(j.get("created_at")),"posted",",".join(j.get("tags") or []),j))
            if not data.get("links",{}).get("next"): break
    return out


async def adzuna(_board: str, _company: str, profile: dict) -> list[Job]:
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
        raise ValueError("Adzuna is not configured in .env")
    query=" OR ".join((profile.get("target_titles") or ["data scientist"])[:4])
    location=", ".join((profile.get("locations") or ["India"])[:3])
    url="https://api.adzuna.com/v1/api/jobs/in/search/1"
    params={"app_id":settings.ADZUNA_APP_ID,"app_key":settings.ADZUNA_APP_KEY,"what":query,"where":location,
            "results_per_page":50,"sort_by":"date","content-type":"application/json"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        data=(await client.get(url,params=params)).raise_for_status().json()
    return [Job(key("adzuna",str(j.get("id") or j.get("redirect_url"))),"adzuna","India",j.get("title",""),
        (j.get("company") or {}).get("display_name",""),(j.get("location") or {}).get("display_name",""),
        clean_html(j.get("description","")),j.get("redirect_url",""),iso(j.get("created")),"posted",
        j.get("contract_type",""),j) for j in data.get("results",[]) if j.get("redirect_url")]


async def jooble(_board: str, _company: str, profile: dict) -> list[Job]:
    if not settings.JOOBLE_API_KEY: raise ValueError("Jooble is not configured in .env")
    keywords=" OR ".join((profile.get("target_titles") or ["data scientist"])[:4])
    location=", ".join((profile.get("locations") or ["India"])[:3])
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        data=(await client.post(f"https://jooble.org/api/{settings.JOOBLE_API_KEY}",
            json={"keywords":keywords,"location":location,"page":1,"ResultOnPage":50})).raise_for_status().json()
    return [Job(key("jooble",str(j.get("id") or j.get("link"))),"jooble","global",j.get("title",""),
        j.get("company",""),j.get("location",""),clean_html(j.get("snippet","")),j.get("link",""),
        iso(j.get("updated")),"updated",j.get("type",""),j) for j in data.get("jobs",[]) if j.get("link")]


async def remotive(_board: str, _company: str, profile: dict) -> list[Job]:
    """Remotive public API: documented, keyless, remote-first listings worldwide."""
    titles=(profile.get("target_titles") or ["developer"])[:2]
    out=[];seen=set()
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for title in titles:
            data=(await client.get("https://remotive.com/api/remote-jobs",params={"limit":60,"title":title})).raise_for_status().json()
            for j in data.get("jobs",[]):
                jid=str(j.get("id") or j.get("url"))
                if jid in seen:continue
                seen.add(jid)
                out.append(Job(key("remotive",jid),"remotive","Remotive",j.get("title",""),j.get("company_name",""),
                    j.get("candidate_required_location","") or "Remote",clean_html(j.get("description","")),j.get("url",""),
                    iso(j.get("publication_date")),"posted",j.get("job_type","") or "",j))
    return [x for x in out if x.url]


async def remoteok(_board: str, _company: str, _profile: dict) -> list[Job]:
    """RemoteOK public API: keyless tech-remote feed (first element is a legal notice)."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=False, headers={"User-Agent":"KarnaOS/1.0 (career assistant)"}) as client:
        data=(await client.get("https://remoteok.com/api")).raise_for_status().json()
    out=[]
    for j in data if isinstance(data,list) else []:
        if not isinstance(j,dict) or not (j.get("position") or j.get("url")):continue
        jid=str(j.get("id") or j.get("slug") or j.get("url"))
        out.append(Job(key("remoteok",jid),"remoteok","RemoteOK",j.get("position",""),j.get("company",""),
            j.get("location","") or "Remote",clean_html(j.get("description","")),j.get("url","") or j.get("apply_url",""),
            iso(j.get("date")),"posted",j.get("type","") or "",j))
    return [x for x in out if x.url][:80]


async def jobicy(_board: str, _company: str, _profile: dict) -> list[Job]:
    """Jobicy public API v2: keyless remote jobs across industries."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        data=(await client.get("https://jobicy.com/api/v2/remote-jobs",params={"count":50})).raise_for_status().json()
    out=[]
    for j in data.get("jobs",[]):
        jid=str(j.get("id") or j.get("url"))
        out.append(Job(key("jobicy",jid),"jobicy","Jobicy",j.get("jobTitle",""),j.get("companyName",""),
            "Remote",clean_html(j.get("jobDescription","") or j.get("jobExcerpt","")),j.get("url",""),
            iso(j.get("pubDate")),"posted",j.get("jobLevel","") or "",j))
    return [x for x in out if x.url]


async def himalayas(_board: str, _company: str, _profile: dict) -> list[Job]:
    """Himalayas public API: keyless remote jobs feed."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        data=(await client.get("https://himalayas.app/jobs/api",params={"limit":60})).raise_for_status().json()
    out=[]
    for j in data.get("jobs",[]):
        loc="Remote"
        restrictions=j.get("locationRestrictions")
        if isinstance(restrictions,list) and restrictions:
            loc=", ".join((x.get("name") if isinstance(x,dict) else str(x)) or "" for x in restrictions).strip(", ") or "Remote"
        jid=str(j.get("guid") or j.get("applicationLink") or j.get("title"))
        out.append(Job(key("himalayas",jid),"himalayas","Himalayas",j.get("title",""),j.get("companyName",""),loc,
            clean_html(j.get("descriptionPlain","") or j.get("excerpt","")),j.get("applicationLink","") or j.get("guid",""),
            iso(j.get("pubDate")),"posted",j.get("employmentType","") or "",j))
    return [x for x in out if x.url]


async def usajobs(_board: str, _company: str, profile: dict) -> list[Job]:
    if not settings.USAJOBS_API_KEY or not settings.USAJOBS_EMAIL:
        raise ValueError("USAJOBS is not configured in .env")
    params={"Keyword":(profile.get("target_titles") or ["data scientist"])[0],"ResultsPerPage":50}
    headers={"User-Agent":settings.USAJOBS_EMAIL,"Authorization-Key":settings.USAJOBS_API_KEY}
    async with httpx.AsyncClient(timeout=30,follow_redirects=False,headers=headers) as client:
        data=(await client.get("https://data.usajobs.gov/api/search",params=params)).raise_for_status().json()
    items=((data.get("SearchResult") or {}).get("SearchResultItems") or []); out=[]
    for item in items:
        j=item.get("MatchedObjectDescriptor") or {}; jid=str(j.get("PositionID") or j.get("PositionURI"))
        loc=", ".join(j.get("PositionLocationDisplay") or [])
        out.append(Job(key("usajobs",jid),"usajobs","United States Federal Government",j.get("PositionTitle",""),
            (j.get("OrganizationName") or j.get("DepartmentName","")),loc,clean_html(j.get("QualificationSummary","")),
            j.get("PositionURI",""),iso(j.get("PublicationStartDate")),"posted",
            ", ".join(j.get("PositionSchedule") or []),j))
    return [x for x in out if x.url]


PROVIDERS = {
    "greenhouse":greenhouse, "lever":lever, "ashby":ashby,
    "smartrecruiters":smartrecruiters, "recruitee":recruitee,
    "arbeitnow":arbeitnow, "adzuna":adzuna, "jooble":jooble, "usajobs":usajobs,
    "remotive":remotive, "remoteok":remoteok, "jobicy":jobicy, "himalayas":himalayas,
}

GLOBAL_PROVIDERS={"arbeitnow","adzuna","jooble","usajobs","remotive","remoteok","jobicy","himalayas"}

async def fetch_jobs(provider: str, board: str, company: str, profile: dict) -> list[Job]:
    if provider not in PROVIDERS: raise ValueError(f"Unsupported provider: {provider}")
    return await PROVIDERS[provider](board,company,profile)
