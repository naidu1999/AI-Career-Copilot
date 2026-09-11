from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class User(BaseModel):
    id: Optional[str] = None
    full_name: str
    email: EmailStr

    current_designation: Optional[str] = None
    total_experience: Optional[float] = None
    relevant_ai_ml_experience: Optional[float] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None