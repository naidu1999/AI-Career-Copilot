from backend.ai.openrouter import OpenRouterService
from backend.db.schemas.ai_resume import AIResumeResult
from backend.prompts.resume_parsing import (
    UNIVERSAL_RESUME_SYSTEM_PROMPT,
    build_resume_parsing_prompt,
)


class AIResumeParser:
    def __init__(self) -> None:
        self.openrouter_service = OpenRouterService()

    def parse(
        self,
        resume_text: str,
        model: str,
    ) -> AIResumeResult:
        cleaned_text = resume_text.strip()

        if not cleaned_text:
            raise ValueError("Resume text cannot be empty")

        messages = [
            {
                "role": "system",
                "content": UNIVERSAL_RESUME_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_resume_parsing_prompt(cleaned_text),
            },
        ]

        return self.openrouter_service.structured_chat(
            messages=messages,
            model=model,
            response_schema=AIResumeResult,
        )