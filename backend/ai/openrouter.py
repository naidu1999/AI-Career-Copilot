from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from backend.core.config import settings


SchemaType = TypeVar(
    "SchemaType",
    bound=BaseModel,
)


class OpenRouterService:
    def __init__(self) -> None:
        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY is missing from the .env file"
            )

        self.client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        response_schema: type[SchemaType],
    ) -> SchemaType:
        if not model:
            raise ValueError(
                "OPENROUTER_MODEL is missing from the .env file"
            )

        schema = response_schema.model_json_schema()

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "karna_resume_result",
                    "strict": True,
                    "schema": schema,
                },
            },
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError(
                "The selected AI model returned an empty response"
            )

        return response_schema.model_validate_json(content)