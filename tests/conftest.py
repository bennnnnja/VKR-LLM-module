from __future__ import annotations

import json
import os

# Тесты используют fakeredis вместо реального брокера; зафиксируем безопасный API_KEY,
# который тесты будут передавать в X-API-Key.
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AVAILABLE_MODELS", "qwen2.5:32b-instruct")
os.environ.setdefault("FALLBACK_STRATEGY", "stub")
os.environ.setdefault("FALLBACK_MODEL", "qwen2.5:32b-instruct")

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app import deps
from app.config import settings
from app.main import app
from app.services import job_store as job_store_module
from app.services.embedding_service import EmbeddingService
from app.services.llm_client import GenerateMeta


# ───────────────────── Fake LLM-инфраструктура ─────────────────────

DEFAULT_EVAL_OUTPUT = {
    "total_score": 78,
    "criteria": [
        {"name": "Точность",     "score": 80, "comment": "fake comment"},
        {"name": "Полнота",      "score": 70, "comment": "fake comment"},
        {"name": "Логика",       "score": 85, "comment": "fake comment"},
        {"name": "Терминология", "score": 75, "comment": "fake comment"},
    ],
    "summary": "fake summary from FakeOllamaClient",
    "strengths": ["fake strength"],
    "weaknesses": ["fake weakness"],
}


class FakeOllamaClient:
    """Скриптуемый клиент: тест может протолкнуть конкретный ответ или ошибку.
    Если очередь пуста — отдаёт DEFAULT_EVAL_OUTPUT как валидный JSON.
    """

    def __init__(self) -> None:
        self._scripted: list = []
        self.calls: list[dict] = []

    def push_response(self, raw: str, meta: GenerateMeta | None = None) -> None:
        self._scripted.append(("ok", raw, meta or GenerateMeta(
            duration_ms=120, eval_count=50, prompt_eval_count=10
        )))

    def push_error(self, exc: Exception) -> None:
        self._scripted.append(("err", exc))

    async def generate(self, prompt: str, model: str, format: str | None = "json"):
        self.calls.append({"prompt": prompt, "model": model, "format": format})
        if self._scripted:
            entry = self._scripted.pop(0)
            if entry[0] == "ok":
                return entry[1], entry[2]
            raise entry[1]
        return json.dumps(DEFAULT_EVAL_OUTPUT), GenerateMeta(
            duration_ms=120, eval_count=50, prompt_eval_count=10
        )

    async def embeddings(self, prompt: str, model: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def aclose(self) -> None:
        pass


class FakeEmbeddingService:
    """По умолчанию ничего не возвращает (None) — постпроцесс пропускается.
    Тест может прописать конкретные вектора через push().
    """

    def __init__(self) -> None:
        self._scripted: list = []
        self.calls: list = []

    def push(self, value):
        self._scripted.append(value)

    async def embed(self, text: str, model: str):
        self.calls.append({"text": text, "model": model})
        if self._scripted:
            return self._scripted.pop(0)
        return None

    @staticmethod
    def cosine_similarity(a, b):
        return EmbeddingService.cosine_similarity(a, b)


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """Подмена sync и async redis на fakeredis с общим бекендом.

    Каждый from_url возвращает НОВЫЙ FakeRedis (общий FakeServer), чтобы
    избежать привязки aioredis-connection к конкретному event loop —
    Celery-таск делает свой asyncio.run() и работает в новом цикле.
    """

    server = fakeredis.FakeServer()

    def _from_url_sync(*_args, **_kwargs):
        return fakeredis.FakeRedis(server=server, decode_responses=True)

    def _from_url_async(*_args, **_kwargs):
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    monkeypatch.setattr(job_store_module.sync_redis, "from_url", _from_url_sync)
    monkeypatch.setattr(job_store_module.async_redis, "from_url", _from_url_async)

    yield server


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """Глобальная подмена OllamaClient и EmbeddingService.

    Любой тест может получить fake через параметр fake_llm и
    управлять ответами: fake_llm.ollama.push_response(...) и т.п.
    """
    fake_ollama = FakeOllamaClient()
    fake_embed = FakeEmbeddingService()

    deps.reset_singletons_for_test()
    monkeypatch.setattr("app.deps.get_ollama_client", lambda: fake_ollama)
    monkeypatch.setattr("app.deps.get_embedding_service", lambda: fake_embed)

    # Также убираем искусственные sleeps в evaluate-stub-ветке
    async def _no_async_sleep(_):
        return None
    monkeypatch.setattr("app.workers.evaluate_task.asyncio.sleep", _no_async_sleep)

    class Holder:
        ollama = fake_ollama
        embed = fake_embed

    yield Holder


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api_key() -> str:
    return settings.auth.api_key
