"""Task-aware multi-provider AI routing with cooldowns and observable failover."""
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.core.config_new import settings
from backend.db.local import execute, now, rows, uid

TASKS=("resume-extraction","evidence-normalization","recruiter-review","tailor","cover-letter","interview-prep","star-coach","summary","dossier","gap-analysis","answer-sheet")

@dataclass
class Provider:
    id:str;name:str;adapter:str;base_url:str;key:str;model:str;is_local:bool=False;is_paid:bool=False;priority:int=100

def configured_providers()->list[Provider]:
    providers=[]
    if settings.AI_PROVIDER!="rules" and settings.AI_MODEL:
        providers.append(Provider("legacy","Configured gateway","openai",settings.AI_BASE_URL,settings.AI_API_KEY,settings.AI_MODEL,settings.AI_PROVIDER=="ollama",False,20))
    if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_MODEL:
        providers.append(Provider("anthropic","Anthropic","anthropic","https://api.anthropic.com",settings.ANTHROPIC_API_KEY,settings.ANTHROPIC_MODEL,False,True,30))
    if settings.OPENAI_API_KEY and settings.OPENAI_MODEL:
        providers.append(Provider("openai","OpenAI API","openai",settings.OPENAI_BASE_URL,settings.OPENAI_API_KEY,settings.OPENAI_MODEL,False,True,40))
    if settings.GROQ_API_KEY:
        providers.append(Provider("groq","Groq (free tier)","openai",settings.GROQ_BASE_URL,settings.GROQ_API_KEY,settings.GROQ_MODEL,False,False,35))
    if settings.GEMINI_API_KEY and settings.GEMINI_MODEL:
        providers.append(Provider("gemini","Google Gemini","gemini","https://generativelanguage.googleapis.com",settings.GEMINI_API_KEY,settings.GEMINI_MODEL,False,False,50))
    if settings.OPENROUTER_API_KEY and settings.OPENROUTER_MODEL:
        providers.append(Provider("openrouter","OpenRouter","openai","https://openrouter.ai/api/v1",settings.OPENROUTER_API_KEY,settings.OPENROUTER_MODEL,False,False,60))
    if settings.CEREBRAS_API_KEY:
        providers.append(Provider("cerebras","Cerebras (free tier)","openai",settings.CEREBRAS_BASE_URL,settings.CEREBRAS_API_KEY,settings.CEREBRAS_MODEL,False,False,65))
    if settings.MISTRAL_API_KEY:
        providers.append(Provider("mistral","Mistral (free tier)","openai",settings.MISTRAL_BASE_URL,settings.MISTRAL_API_KEY,settings.MISTRAL_MODEL,False,False,70))
    if settings.POLLINATIONS_ENABLED:
        providers.append(Provider("pollinations","Pollinations (no key needed)","openai",settings.POLLINATIONS_BASE_URL,"",settings.POLLINATIONS_MODEL,False,False,80))
    if settings.AI_LOCAL_FALLBACK and settings.OLLAMA_MODEL:
        providers.append(Provider("ollama","Local Ollama","openai",settings.OLLAMA_BASE_URL,"ollama",settings.OLLAMA_MODEL,True,False,999))
    return providers

def ensure_router(owner_id:str)->list[Provider]:
    providers=configured_providers();stamp=now()
    for p in providers:
        execute("""INSERT INTO ai_providers (id,owner_id,name,adapter,base_url,api_key_env,model,enabled,is_local,is_paid,priority,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(owner_id,name) DO UPDATE SET adapter=excluded.adapter,base_url=excluded.base_url,
        model=excluded.model,is_local=excluded.is_local,is_paid=excluded.is_paid""",
        (f"{owner_id}:{p.id}",owner_id,p.name,p.adapter,p.base_url,"configured in environment",p.model,1,int(p.is_local),int(p.is_paid),p.priority,stamp))
        p.id=f"{owner_id}:{p.id}"
    existing=rows("SELECT task FROM ai_routes WHERE owner_id=?",(owner_id,));known={x["task"] for x in existing}
    ids=[p.id for p in sorted(providers,key=lambda x:(x.is_local,x.is_paid,x.priority))]
    for task in TASKS:
        if task not in known:
            execute("INSERT INTO ai_routes (id,owner_id,task,provider_ids,mode,allow_paid,max_attempts,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (uid(),owner_id,task,json.dumps(ids),"automatic",int(settings.AI_ALLOW_PAID),settings.AI_MAX_ATTEMPTS,stamp))
    return providers

def route_for(owner_id:str,task:str,providers:list[Provider])->tuple[list[Provider],dict]:
    found=rows("SELECT * FROM ai_routes WHERE owner_id=? AND task=?",(owner_id,task))
    route=found[0] if found else {"provider_ids":"[]","mode":"automatic","allow_paid":int(settings.AI_ALLOW_PAID),"max_attempts":settings.AI_MAX_ATTEMPTS}
    order=json.loads(route.get("provider_ids") or "[]");by_id={p.id:p for p in providers}
    ordered=[by_id[x] for x in order if x in by_id]+[p for p in providers if p.id not in order]
    if not route.get("allow_paid"):ordered=[p for p in ordered if not p.is_paid]
    health={x["id"]:x for x in rows("SELECT * FROM ai_providers WHERE owner_id=?",(owner_id,))}
    current=datetime.now(timezone.utc)
    ordered=[p for p in ordered if health.get(p.id,{}).get("enabled",1) and (not health.get(p.id,{}).get("cooldown_until") or datetime.fromisoformat(health[p.id]["cooldown_until"])<=current)]
    return ordered,route

async def request_provider(provider:Provider,messages:list[dict[str,str]])->str:
    timeout=httpx.Timeout(settings.AI_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider.adapter=="anthropic":
            system="\n".join(x["content"] for x in messages if x["role"]=="system")
            body={"model":provider.model,"max_tokens":4000,"temperature":0,"system":system,"messages":[x for x in messages if x["role"]!="system"]}
            response=await client.post(provider.base_url.rstrip("/")+"/v1/messages",headers={"x-api-key":provider.key,"anthropic-version":"2023-06-01","content-type":"application/json"},json=body)
            response.raise_for_status();return "".join(x.get("text","") for x in response.json().get("content",[]))
        if provider.adapter=="gemini":
            text="\n\n".join(f"{x['role'].upper()}: {x['content']}" for x in messages)
            response=await client.post(f"{provider.base_url.rstrip('/')}/v1beta/models/{provider.model}:generateContent",params={"key":provider.key},json={"contents":[{"parts":[{"text":text}]}],"generationConfig":{"temperature":0}})
            response.raise_for_status();return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        response=await client.post(provider.base_url.rstrip("/")+"/chat/completions",headers={"Authorization":f"Bearer {provider.key}","Content-Type":"application/json"} if provider.key else {"Content-Type":"application/json"},json={"model":provider.model,"messages":messages,"temperature":0})
        response.raise_for_status();return response.json()["choices"][0]["message"]["content"]

def retryable(exc:Exception)->tuple[bool,str,int|None]:
    if isinstance(exc,httpx.HTTPStatusError):
        status=exc.response.status_code;retry_after=exc.response.headers.get("retry-after")
        seconds=int(retry_after) if retry_after and retry_after.isdigit() else None
        return status in {408,409,429,500,502,503,504},f"HTTP {status}",seconds
    return isinstance(exc,(httpx.TimeoutException,httpx.NetworkError)),exc.__class__.__name__,None

class AIRouter:
    def __init__(self,owner_id:str):self.owner_id=owner_id
    @property
    def enabled(self)->bool:return bool(configured_providers()) or settings.POLLINATIONS_ENABLED
    async def chat(self,task:str,messages:list[dict[str,str]])->dict[str,Any]:
        providers=ensure_router(self.owner_id);route,config=route_for(self.owner_id,task,providers)
        if not route:raise RuntimeError("No healthy AI provider is configured for this task")
        errors=[];max_attempts=max(1,min(int(config.get("max_attempts") or 4),len(route)))
        for attempt,provider in enumerate(route[:max_attempts],1):
            started=time.perf_counter()
            try:
                content=await request_provider(provider,messages)
                if not content.strip():raise ValueError("Provider returned an empty response")
                latency=(time.perf_counter()-started)*1000
                execute("UPDATE ai_providers SET health_status='healthy',consecutive_failures=0,cooldown_until=NULL,last_success_at=?,last_error='',average_latency_ms=CASE WHEN requests=0 THEN ? ELSE (average_latency_ms*requests+?)/(requests+1) END,requests=requests+1 WHERE id=?",(now(),latency,latency,provider.id))
                execute("INSERT INTO ai_request_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",(uid(),self.owner_id,task,provider.id,provider.model,"success",latency,attempt,"; ".join(errors),"",now()))
                return {"content":content,"provider":provider.name,"model":provider.model,"attempts":attempt,"fallback_reason":"; ".join(errors)}
            except Exception as exc:
                can_retry,reason,retry_after=retryable(exc);errors.append(f"{provider.name}: {reason}")
                failures=rows("SELECT consecutive_failures FROM ai_providers WHERE id=?",(provider.id,));count=(failures[0]["consecutive_failures"] if failures else 0)+1
                cooldown=retry_after or settings.AI_CIRCUIT_COOLDOWN_SECONDS if count>=settings.AI_CIRCUIT_FAILURES or reason=="HTTP 429" else 0
                until=(datetime.now(timezone.utc)+timedelta(seconds=cooldown)).isoformat() if cooldown else None
                execute("UPDATE ai_providers SET health_status=?,consecutive_failures=?,cooldown_until=?,last_failure_at=?,last_error=?,failures=failures+1,requests=requests+1 WHERE id=?",("cooldown" if cooldown else "degraded",count,until,now(),reason,provider.id))
                if not can_retry and reason in {"HTTP 401","HTTP 403"}:continue
                await asyncio.sleep(min(.25*attempt,1))
        execute("INSERT INTO ai_request_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",(uid(),self.owner_id,task,None,"","failed",0,max_attempts,"; ".join(errors),errors[-1] if errors else "No provider",now()))
        raise RuntimeError("All configured AI routes failed: "+"; ".join(errors))

def router_status(owner_id:str)->dict:
    ensure_router(owner_id)
    providers=rows("SELECT id,name,adapter,model,enabled,is_local,is_paid,priority,health_status,cooldown_until,last_success_at,last_failure_at,last_error,average_latency_ms,requests,failures FROM ai_providers WHERE owner_id=? ORDER BY priority",(owner_id,))
    routes=rows("SELECT id,task,provider_ids,mode,allow_paid,max_attempts,updated_at FROM ai_routes WHERE owner_id=? ORDER BY task",(owner_id,))
    for route in routes:route["provider_ids"]=json.loads(route["provider_ids"])
    return {"preset":settings.AI_ROUTING_PRESET,"providers":providers,"routes":routes}
