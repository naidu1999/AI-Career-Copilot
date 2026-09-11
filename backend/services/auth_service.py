from contextvars import ContextVar
from time import monotonic

import httpx
from fastapi import HTTPException

from backend.core.config_new import settings

current_user_id:ContextVar[str]=ContextVar("current_user_id",default="default")
_sessions:dict[str,tuple[float,dict]]={}

def user_id()->str:return current_user_id.get()
def hosted()->bool:return settings.DEPLOYMENT_MODE.lower()=="hosted"

def auth_headers(token:str)->dict:
    return {"apikey":settings.SUPABASE_PUBLISHABLE_KEY,"Authorization":f"Bearer {token}"}

async def authenticate(token:str)->dict:
    if not token:raise HTTPException(401,"Sign in required")
    cached=_sessions.get(token)
    if cached and cached[0]>monotonic():return cached[1]
    if not settings.SUPABASE_URL or not settings.SUPABASE_PUBLISHABLE_KEY:
        raise HTTPException(503,"Hosted authentication is not configured")
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        response=await client.get(f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user",headers=auth_headers(token))
    if response.status_code!=200:raise HTTPException(401,"Session expired; sign in again")
    user=response.json();_sessions[token]=(monotonic()+60,user);return user

async def password_action(path:str,payload:dict)->dict:
    if not settings.SUPABASE_URL or not settings.SUPABASE_PUBLISHABLE_KEY:
        raise HTTPException(503,"Hosted authentication is not configured")
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        response=await client.post(f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/{path}",headers={"apikey":settings.SUPABASE_PUBLISHABLE_KEY,"Content-Type":"application/json"},json=payload)
    data=response.json() if response.content else {}
    if response.status_code>=400:raise HTTPException(response.status_code,data.get("msg") or data.get("error_description") or "Authentication failed")
    return data

async def revoke(token:str)->None:
    if not token:return
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
            await client.post(f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/logout",headers=auth_headers(token))
    finally:forget(token)

async def delete_auth_user(account_id:str)->None:
    secret=settings.SUPABASE_SECRET_KEY
    if not secret:raise HTTPException(503,"Account deletion requires the server-side Supabase secret")
    headers={"apikey":secret,"Authorization":f"Bearer {secret}"}
    async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
        response=await client.delete(f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{account_id}",headers=headers)
    if response.status_code not in {200,204}:raise HTTPException(502,"Supabase account deletion failed; contact the administrator")

def forget(token:str)->None:_sessions.pop(token,None)
