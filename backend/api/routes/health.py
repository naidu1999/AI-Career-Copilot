from fastapi import APIRouter

from backend.db.client import supabase

router = APIRouter(
    prefix="/database",
    tags=["Database"]
)


@router.get("/health")
async def database_health():
    try:
        # Simple query to verify the connection
        supabase.table("pg_tables").select("*").limit(1).execute()

        return {
            "database": "Connected",
            "status": "OK"
        }

    except Exception as e:
        return {
            "database": "Disconnected",
            "status": "ERROR",
            "message": str(e)
        }