from typing import Any
import httpx

from backend.core.config_new import settings


class AIGateway:
    """Optional OpenAI-compatible gateway for Ollama, LiteLLM or cloud endpoints."""

    @property
    def enabled(self) -> bool:
        return settings.AI_PROVIDER != "rules" and bool(settings.AI_MODEL)

    async def chat(self, messages: list[dict[str, str]], json_schema: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            raise RuntimeError("AI is disabled; configure AI_PROVIDER and AI_MODEL in .env")
        payload: dict[str, Any] = {"model": settings.AI_MODEL, "messages": messages, "temperature": 0}
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "karna_result", "strict": True, "schema": json_schema}}
        headers = {"Authorization": f"Bearer {settings.AI_API_KEY}"}
        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{settings.AI_BASE_URL.rstrip('/')}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

