from __future__ import annotations

import os

# Тесты используют fakeredis вместо реального брокера; зафиксируем безопасный API_KEY,
# который тесты будут передавать в X-API-Key.
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AVAILABLE_MODELS", "qwen2.5:32b-instruct")
os.environ.setdefault("FALLBACK_STRATEGY", "stub")
os.environ.setdefault("FALLBACK_MODEL", "qwen2.5:32b-instruct")

import asyncio
from typing import AsyncIterator

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.deps import get_job_store
from app.main import app
from app.services import job_store as job_store_module
from app.services.job_store import JobStoreAsync


@pytest.fixture(autouse=True)
def patch_redis(monkeypatch):
    """Подменяем sync и async redis на fakeredis с общим бекендом."""

    server = fakeredis.FakeServer()

    fake_sync = fakeredis.FakeRedis(server=server, decode_responses=True)
    fake_async = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)

    def _from_url_sync(*_args, **_kwargs):
        return fake_sync

    def _from_url_async(*_args, **_kwargs):
        return fake_async

    monkeypatch.setattr(job_store_module.sync_redis, "from_url", _from_url_sync)
    monkeypatch.setattr(job_store_module.async_redis, "from_url", _from_url_async)

    yield server


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def api_key() -> str:
    return settings.auth.api_key
