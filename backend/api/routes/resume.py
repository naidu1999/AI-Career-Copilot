from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader

from backend.db.repositories.resume_repository import ResumeRepository
from backend.db.repositories.resume_section_repository import (
    ResumeSectionRepository,
)
from backend.db.schemas.resume import ResumeResponse
from backend.db.schemas.resume_section import ResumeSectionResponse
from backend.services.resume_parser import ResumeParser


router = APIRouter(
    prefix="/resumes",
    tags=["Resumes"],
)

resume_repository = ResumeRepository()
resume_section_repository = ResumeSectionRepository()
resume_parser = ResumeParser()

ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024


@router.post(
    "/upload",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    user_id: UUID = Form(...),
    is_primary: bool = Form(False),
    file: UploadFile = File(...),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF resumes are currently supported",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Resume file must be 5 MB or smaller",
        )

    try:
        pdf_reader = PdfReader(BytesIO(file_bytes))

        extracted_pages = [
            page.extract_text() or ""
            for page in pdf_reader.pages
        ]

        extracted_text = "\n".join(extracted_pages).strip()

        if not extracted_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No readable text was found in the PDF",
            )

        resume_data = {
            "user_id": str(user_id),
            "file_name": file.filename or "resume.pdf",
            "file_type": file.content_type,
            "file_size": len(file_bytes),
            "storage_path": None,
            "extracted_text": extracted_text,
            "parsing_status": "processed",
            "is_primary": is_primary,
        }

        response = resume_repository.create(resume_data)

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Resume metadata could not be saved",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Resume parsing failed: {exc}",
        )


@router.get(
    "/user/{user_id}",
    response_model=list[ResumeResponse],
    status_code=status.HTTP_200_OK,
)
async def get_user_resumes(user_id: UUID):
    try:
        response = resume_repository.get_by_user_id(str(user_id))
        return response.data

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post(
    "/{resume_id}/parse",
    response_model=ResumeSectionResponse,
    status_code=status.HTTP_200_OK,
)
async def parse_resume(resume_id: UUID):
    try:
        resume_response = resume_repository.get_by_id(str(resume_id))

        if not resume_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume not found",
            )

        resume_record = resume_response.data[0]
        extracted_text = resume_record.get("extracted_text")

        if not extracted_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The resume does not contain extracted text",
            )

        parsed_sections = resume_parser.parse(extracted_text)

        section_data = {
            "resume_id": str(resume_id),
            **parsed_sections,
        }

        existing_sections = (
            resume_section_repository.get_by_resume_id(str(resume_id))
        )

        if existing_sections.data:
            response = resume_section_repository.update(
                str(resume_id),
                parsed_sections,
            )
        else:
            response = resume_section_repository.create(section_data)

        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Parsed resume sections could not be saved",
            )

        return response.data[0]

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )