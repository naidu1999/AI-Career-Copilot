from fastapi import APIRouter

from backend.api.routes.database import router as database_router
from backend.api.routes.health import router as health_router
from backend.api.routes.resume import router as resume_router
from backend.api.routes.users import router as users_router


api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(database_router)
api_router.include_router(users_router)
api_router.include_router(resume_router)