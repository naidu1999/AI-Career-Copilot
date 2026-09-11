from fastapi import APIRouter

from backend.db.client import supabase

router = APIRouter(
    prefix="/database",
    tags=["Database"]
)


@router.get("/health")
async def database_health():
    try:
        response = supabase.table("users").select("*").limit(1).execute()

        return {
            "database": "Connected",
            "status": "OK",
            "rows_checked": len(response.data)
        }

    except Exception as e:
        return {
            "database": "Disconnected",
            "status": "ERROR",
            "message": str(e)
        }