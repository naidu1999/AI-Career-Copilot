from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    current_designation: str | None = None
    total_experience: float | None = None
    relevant_ai_ml_experience: float | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    current_designation: str | None = None
    total_experience: float | None = None
    relevant_ai_ml_experience: float | None = None


class UserResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    current_designation: str | None = None
    total_experience: float | None = None
    relevant_ai_ml_experience: float | None = None
    created_at: datetime
    updated_at: datetime