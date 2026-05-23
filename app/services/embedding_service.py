from __future__ import annotations

import math
from typing import Optional

from loguru import logger

from app.services.llm_client import LLMError, OllamaClient


class EmbeddingService:
    """Опциональная постобработка: косинусная близость через Ollama embeddings.

    Если эмбеддер недоступен — embed() возвращает None и пишет warning,
    но не падает. Это позволяет основной evaluate-результат сохраниться
    даже когда эмбеддер выключен.
    """

    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    async def embed(self, text: str, model: str) -> Optional[list[float]]:
        if not text:
            return None
        try:
            return await self._client.embeddings(text, model=model)
        except LLMError as exc:
            logger.warning("embedding unavailable for model {}: {}", model, exc)
            return None

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for x, y in zip(a, b):
            dot += x * y
            norm_a += x * x
            norm_b += y * y
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
