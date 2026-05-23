from __future__ import annotations

from typing import AsyncIterator

from app.services.embedding_service import EmbeddingService
from app.services.job_store import JobStoreAsync
from app.services.llm_client import OllamaClient

# Синглтоны на процесс: один OllamaClient → один общий семафор concurrency.
# Если бы клиент пересоздавался при каждом вызове, ограничение
# LLM_MAX_CONCURRENT не работало бы, т.к. семафор у каждого инстанса свой.
_ollama_client: OllamaClient | None = None
_embedding_service: EmbeddingService | None = None


def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(client=get_ollama_client())
    return _embedding_service


def reset_singletons_for_test() -> None:
    """Сброс синглтонов между тестами — нужен только в тестовом окружении."""
    global _ollama_client, _embedding_service
    _ollama_client = None
    _embedding_service = None


async def get_job_store() -> AsyncIterator[JobStoreAsync]:
    store = JobStoreAsync()
    try:
        yield store
    finally:
        await store.close()
