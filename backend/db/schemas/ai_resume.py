from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )


class TextCorrection(StrictModel):
    original_text: str
    normalized_text: str
    correction_type: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    requires_user_review: bool = False


class PersonalField(StrictModel):
    value: str | None = None
    original_text: str | None = None
    source_text: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    correction_applied: bool = False
    correction_confidence: float = Field(default=0, ge=0, le=1)


class PersonalDetails(StrictModel):
    full_name: PersonalField
    email: PersonalField
    phone: PersonalField
    location: PersonalField

    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other_links: list[str] = Field(default_factory=list)


class SummaryData(StrictModel):
    normalized_text: str | None = None
    original_text: str | None = None
    source_section: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ] = "needs_user_verification"


class DomainData(StrictModel):
    domain: str
    classification: Literal["primary", "secondary"]
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class SeniorityData(StrictModel):
    level: str | None = None
    source_text: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ] = "needs_user_verification"


class SkillData(StrictModel):
    name: str
    original_text: str
    category: str | None = None
    category_is_inferred: bool = False
    source_section: str
    source_text: str
    confidence: float = Field(ge=0, le=1)

    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ]

    correction_applied: bool = False
    correction_confidence: float = Field(default=0, ge=0, le=1)


class DateData(StrictModel):
    original: str | None = None
    normalized: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class ExperienceData(StrictModel):
    organization: str | None = None
    role: str | None = None
    location: str | None = None

    start_date: DateData
    end_date: DateData
    is_current: bool = False

    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)

    source_section: str
    source_text: str
    confidence: float = Field(ge=0, le=1)

    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ]

    requires_user_review: bool = False


class EducationData(StrictModel):
    institution: str | None = None
    qualification: str | None = None
    field_of_study: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    grade: str | None = None

    source_section: str
    source_text: str
    confidence: float = Field(ge=0, le=1)

    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ]

    requires_user_review: bool = False


class ProjectData(StrictModel):
    name: str | None = None
    description: str | None = None
    role: str | None = None

    technologies: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)

    deployment: str | None = None
    links: list[str] = Field(default_factory=list)

    source_section: str
    source_text: str
    confidence: float = Field(ge=0, le=1)

    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ]

    requires_user_review: bool = False


class GenericEvidenceItem(StrictModel):
    title: str | None = None
    description: str | None = None
    source_section: str | None = None
    source_text: str
    confidence: float = Field(ge=0, le=1)

    verification_status: Literal[
        "document_verified",
        "needs_user_verification",
    ]

    requires_user_review: bool = False


class DomainSpecificSection(StrictModel):
    original_heading: str
    normalized_heading: str
    section_type: Literal["domain_specific"] = "domain_specific"

    items: list[str] = Field(default_factory=list)
    raw_text: str

    confidence: float = Field(ge=0, le=1)
    requires_user_review: bool = False


class ParserMetadata(StrictModel):
    parser_type: Literal["llm"] = "llm"
    resume_language: str | None = None

    overall_confidence: float = Field(ge=0, le=1)
    requires_user_review: bool = False

    low_confidence_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unsupported_or_unclassified_content: list[str] = Field(
        default_factory=list
    )


class AIResumeResult(StrictModel):
    personal_details: PersonalDetails
    summary: SummaryData

    detected_domains: list[DomainData] = Field(default_factory=list)
    seniority: SeniorityData

    skills: list[SkillData] = Field(default_factory=list)
    experience: list[ExperienceData] = Field(default_factory=list)
    education: list[EducationData] = Field(default_factory=list)
    projects: list[ProjectData] = Field(default_factory=list)

    certifications: list[GenericEvidenceItem] = Field(default_factory=list)
    achievements: list[GenericEvidenceItem] = Field(default_factory=list)
    publications: list[GenericEvidenceItem] = Field(default_factory=list)
    awards: list[GenericEvidenceItem] = Field(default_factory=list)
    languages: list[GenericEvidenceItem] = Field(default_factory=list)
    licenses: list[GenericEvidenceItem] = Field(default_factory=list)

    volunteer_experience: list[GenericEvidenceItem] = Field(
        default_factory=list
    )

    professional_memberships: list[GenericEvidenceItem] = Field(
        default_factory=list
    )

    domain_specific_sections: list[DomainSpecificSection] = Field(
        default_factory=list
    )

    corrections: list[TextCorrection] = Field(default_factory=list)
    parser_metadata: ParserMetadata