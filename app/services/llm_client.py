from __future__ import annotations

# STUB: реальная реализация появится в фазах 3-4 (вызов Ollama через httpx,
# concurrency-semaphore, таймауты, retry, format=json). На фазе 1 файл
# существует только чтобы зафиксировать структуру модуля.

import asyncio
from dataclasses import dataclass

from app.config import settings


@dataclass
class LLMResponse:
    raw: str
    duration_ms: int


class OllamaClient:
    """STUB-клиент. На фазе 1 реальные вызовы не выполняются."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.ollama.llm_max_concurrent)

    async def generate(self, model: str, prompt: str) -> LLMResponse:
        raise NotImplementedError(
            "OllamaClient.generate появится в фазе 3 (реальный вызов Ollama)."
        )
