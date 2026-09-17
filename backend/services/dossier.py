"""Fit Dossier: a structured evaluation of one posting against one candidate.

The global score is a holistic 1-5 judgement across five dimensions, not an
arithmetic average. Posting legitimacy is a separate, score-neutral signal.
Requirement weights record whether importance is stated in the posting or
estimated; an estimate can never be rated critical. Everything is grounded in
verified evidence and the candidate's own story bank.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.services.discovery import ATS_PROVIDERS
from backend.services.recruiter import recruiter_context

DIMENSIONS=("role_fit","evidence_strength","growth_value","practical_fit","risk_level")
VERDICTS={"prioritize","strong","possible","skip"}
SCAM_MARKERS=re.compile(r"(?:registration fee|pay(?:ment)? (?:for|to) (?:apply|training|kit)|whatsapp|telegram only|no (?:interview|experience) needed|earn [0-9$]+ (?:per day|daily)|crypto (?:investment|wallet)|processing fee)",re.I)

def legitimacy_check(job:dict)->dict:
    """Deterministic trust signals. Never affects the global score."""
    signals:list[str]=[]
    provider=str(job.get("provider") or "")
    if provider in ATS_PROVIDERS:signals.append("Sourced from an official company ATS feed")
    elif provider=="manual":signals.append("Added manually by you from an official page")
    else:signals.append(f"Aggregator source ({provider or 'unknown'}); verify on the official careers page")
    posted=str(job.get("posted_at") or "")
    if posted:
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(posted.replace("Z","+00:00"))).days
            signals.append(f"Posted about {age} days ago" if age>=0 else "Posting date is in the future")
            if age>60:signals.append("Posting looks stale; confirm the role is still open")
        except ValueError:signals.append("Posting date could not be parsed")
    else:signals.append("No posting date available")
    repost=int(job.get("repost_count") or 0);dups=int(job.get("duplicate_count") or 0)
    if repost>=2 or dups>=3:signals.append(f"Seen {max(repost,1)} times across sources; repeated postings can signal a ghost role")
    description=str(job.get("description") or "")
    hits=SCAM_MARKERS.findall(description)
    if hits:signals.append("Suspicious wording in the description: "+", ".join(sorted({h.lower() for h in hits}))[:120])
    if not str(job.get("company") or "").strip():signals.append("Company name missing")
    if not str(job.get("url") or "").strip():signals.append("No official application link")
    bad=sum(1 for s in signals if any(w in s.lower() for w in ("suspicious","ghost","stale","missing","no official","future","could not")))
    if hits:bad+=1  # financial scam wording is a strong signal on its own
    assessment="questionable" if bad>=2 else "unclear" if bad==1 else "trustworthy"
    return {"assessment":assessment,"signals":signals[:8],"note":"Automatic trust check; always open the official page before applying."}

def _clamp(v:Any,lo:float,hi:float,default:float)->float:
    try:x=float(v)
    except (TypeError,ValueError):return default
    return round(min(hi,max(lo,x)),1)

def _dim(label:str,value:Any,note:Any)->dict:
    return {"score":_clamp(value,1,5,3),"note":str(note or "").strip()[:180] or f"{label.replace('_',' ').title()} assessment."}

def _normalise(data:dict)->dict:
    dims={k:_dim(k,(data.get("dimensions") or {}).get(k,{}).get("score"),(data.get("dimensions") or {}).get(k,{}).get("note")) for k in DIMENSIONS}
    verdict=str(data.get("verdict") or "").strip().lower().split()[0] if str(data.get("verdict") or "").strip() else "possible"
    if verdict not in VERDICTS:verdict="prioritize" if _clamp(data.get("global_score"),1,5,3)>=4.5 else "possible"
    reqs=[]
    for r in (data.get("requirements") or [])[:12]:
        if not isinstance(r,dict) or not str(r.get("requirement","")).strip():continue
        weight=str(r.get("weight") or "helpful").lower()
        if weight not in {"critical","helpful","peripheral"}:weight="helpful"
        if str(r.get("basis") or "estimated").lower()!="stated":
            basis="estimated"
            if weight=="critical":weight="helpful"  # an estimate can never be critical
        else:basis="stated"
        status=str(r.get("status") or "partial").lower()
        reqs.append({"requirement":str(r["requirement"]).strip()[:160],"weight":weight,"basis":basis,"status":status if status in {"met","partial","missing"} else "partial"})
    return {
        "global_score":_clamp(data.get("global_score"),1,5,3),
        "verdict":verdict,
        "dimensions":dims,
        "requirements":reqs,
        "interview_focus":[str(x).strip()[:140] for x in (data.get("interview_focus") or [])[:6] if str(x).strip()],
        "recommended_actions":[str(x).strip()[:160] for x in (data.get("recommended_actions") or [])[:5] if str(x).strip()],
    }

def parse_dossier_json(text:str)->dict|None:
    match=re.search(r"\{.*\}",str(text),re.S)
    if not match:return None
    try:data=json.loads(match.group(0))
    except json.JSONDecodeError:return None
    if not isinstance(data,dict):return None
    return _normalise(data)

def basic_dossier(job:dict,profile:dict,match:dict|None)->dict:
    """Deterministic dossier when no AI is configured — honest and basic."""
    m=match or {"components":{},"missing_skills":[],"classification":"review","score":50}
    c=m.get("components") or {};missing=m.get("missing_skills") or []
    dims={
        "role_fit":_dim("role_fit",min(5,(c.get("title") or 50)/20),"Role-family compatibility from the transparent matcher."),
        "evidence_strength":_dim("evidence_strength",min(5,(c.get("evidence") or 50)/20),"How much of your verified evidence this role can use."),
        "growth_value":_dim("growth_value",3,"Basic estimate; run an AI dossier for a researched view."),
        "practical_fit":_dim("practical_fit",min(5,((c.get("location") or 50)+(c.get("experience") or 50))/40),"Location and experience eligibility."),
        "risk_level":_dim("risk_level",max(1,5-len(missing)),f"{len(missing)} gap(s) against the posting."),
    }
    verdict="skip" if m.get("classification")=="ineligible" else "possible" if m.get("classification") in {"review","low_match"} else "strong"
    score=_clamp((m.get("score") or 50)/20,1,5,3)
    reqs=[{"requirement":s,"weight":"helpful","basis":"estimated","status":"missing"} for s in missing[:8]]
    actions={"qualified":["Open the official posting and confirm it is live","Shortlist and generate a tailored resume draft"],"review":["Compare missing skills against your verified evidence","Keep in review; do not apply yet"],"low_match":["Not worth your time right now"],"ineligible":["Blocked by a hard eligibility check; skip"]}
    return {"global_score":score,"verdict":verdict,"dimensions":dims,"requirements":reqs,
            "interview_focus":[s for s in missing[:4]],
            "recommended_actions":actions.get(m.get("classification"),actions["review"])[:3]}

DOSSIER_PROMPT="""You are a senior career strategist evaluating ONE job posting for ONE candidate.
Judge holistically; the global score is NOT an average of the dimensions.
Return ONLY valid JSON, no prose, exactly this shape:
{"global_score":<1.0-5.0 one decimal>,
 "verdict":"<prioritize|strong|possible|skip>",
 "dimensions":{"role_fit":{"score":<1-5>,"note":"<=25 words"},"evidence_strength":{"score":<1-5>,"note":"..."},"growth_value":{"score":<1-5>,"note":"..."},"practical_fit":{"score":<1-5>,"note":"..."},"risk_level":{"score":<1-5>,"note":"..."}},
 "requirements":[{"requirement":"...","weight":"critical|helpful|peripheral","basis":"stated|estimated","status":"met|partial|missing"}],
 "interview_focus":["topic","..."],
 "recommended_actions":["action","..."]}
Rules: posting legitimacy is handled elsewhere, so never let trust affect the scores. A requirement weight can be "critical" only when the posting's own wording demands it (basis "stated"); anything inferred is basis "estimated" and at most "helpful". Ground every judgement only in the candidate material provided. Never invent experience. 4.5+ means you would tell this person to drop everything and prepare; below 3.0 means skip."""

def dossier_prompt(job:dict,profile:dict,verified:list[dict],stories:list[dict],match:dict|None)->str:
    story_block="\n".join(f"- {s['title']} ({s['category']}): S:{s['situation'][:110]} T:{s['task'][:90]} A:{s['action'][:110]} R:{s['result'][:110]}" for s in stories[:8]) or "- None recorded yet"
    evidence_block="\n".join(f"- {v['category']}: {v['normalized_value']}" for v in verified[:40]) or "- None verified yet"
    m=match or {}
    return (f"{DOSSIER_PROMPT}\n\nCANDIDATE CONTEXT:\n{recruiter_context(job,profile,[])}\n\nVERIFIED EVIDENCE:\n{evidence_block}\n\nSTORY BANK:\n{story_block}\n\n"
            f"TRANSPARENT MATCHER (deterministic, for reference):\n{json.dumps({'score':m.get('score'),'components':m.get('components',{}),'missing_skills':m.get('missing_skills',[])[:10],'blockers':m.get('blockers',[])})}\n\nJOB POSTING:\n{json.dumps({k:job.get(k) for k in ('title','company','location','employment_type','description','posted_at')})}")
