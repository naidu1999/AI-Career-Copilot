from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ResumeSectionCreate(BaseModel):
    resume_id: UUID
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)


class ResumeSectionResponse(ResumeSectionCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime