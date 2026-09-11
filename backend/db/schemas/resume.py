from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ResumeCreate(BaseModel):
    user_id: UUID
    file_name: str
    file_type: str
    file_size: int
    storage_path: str | None = None
    extracted_text: str | None = None
    parsing_status: str = "pending"
    is_primary: bool = False


class ResumeResponse(ResumeCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime