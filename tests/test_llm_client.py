from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services.embedding_service import EmbeddingService
from app.services.llm_client import LLMTimeout, LLMUnavailable, OllamaClient


def _make_client(handler, *, timeout=5.0, max_concurrent=2) -> OllamaClient:
    """OllamaClient с подменённым httpx-транспортом."""
    client = OllamaClient(
        base_url="http://ollama.test",
        timeout=timeout,
        max_concurrent=max_concurrent,
    )

    # _get_loop_state создаёт httpx.AsyncClient при первом вызове;
    # переопределяем фабрику, подсовывая MockTransport.
    async def _patch():
        loop = asyncio.get_running_loop()
        client._loop_id = id(loop)
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=timeout
        )
        client._sem = asyncio.Semaphore(max_concurrent)
        client._active = 0
    return client, _patch


async def test_generate_returns_text_and_meta():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:32b-instruct"
        assert body["format"] == "json"
        return httpx.Response(200, json={
            "response": '{"ok": true}',
            "eval_count": 42,
            "prompt_eval_count": 7,
            "total_duration": 123_456_789,
        })

    client, patch = _make_client(handler)
    await patch()
    raw, meta = await client.generate("hello", model="qwen2.5:32b-instruct")
    assert raw == '{"ok": true}'
    assert meta.eval_count == 42
    assert meta.prompt_eval_count == 7
    assert meta.duration_ms >= 0


async def test_generate_raises_llm_unavailable_on_5xx():
    def handler(_request):
        return httpx.Response(503, text="upstream busy")

    client, patch = _make_client(handler)
    await patch()
    with pytest.raises(LLMUnavailable) as ei:
        await client.generate("x", model="m")
    assert "503" in str(ei.value)


async def test_generate_raises_llm_unavailable_on_connect_error():
    def handler(_request):
        raise httpx.ConnectError("cannot connect")

    client, patch = _make_client(handler)
    await patch()
    with pytest.raises(LLMUnavailable):
        await client.generate("x", model="m")


async def test_generate_raises_llm_timeout():
    def handler(_request):
        raise httpx.ReadTimeout("read timeout")

    client, patch = _make_client(handler)
    await patch()
    with pytest.raises(LLMTimeout):
        await client.generate("x", model="m")


async def test_embeddings_returns_vector():
    def handler(request):
        assert request.url.path == "/api/embeddings"
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3, 0.4]})

    client, patch = _make_client(handler)
    await patch()
    vec = await client.embeddings("text", model="emb")
    assert vec == [0.1, 0.2, 0.3, 0.4]


async def test_semaphore_limits_concurrent_calls():
    """Если LLM_MAX_CONCURRENT=2 и пришло 5 запросов одновременно,
    одновременно «в полёте» должно быть не больше 2."""

    inflight = {"now": 0, "max": 0}
    lock = asyncio.Lock()

    async def handler_async(_request):
        async with lock:
            inflight["now"] += 1
            inflight["max"] = max(inflight["max"], inflight["now"])
        await asyncio.sleep(0.05)
        async with lock:
            inflight["now"] -= 1
        return httpx.Response(200, json={"response": "{}"})

    def handler(req):
        # MockTransport принимает sync, но httpx сам обернёт нашу async-логику
        # через handler_async через свой механизм — используем _send-обходной путь.
        raise AssertionError("should not be called directly")

    # MockTransport не умеет async-обработчики напрямую — собираем вручную
    class AsyncMockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await handler_async(request)

    client = OllamaClient(
        base_url="http://ollama.test",
        timeout=5.0,
        max_concurrent=2,
    )
    async def _patch():
        loop = asyncio.get_running_loop()
        client._loop_id = id(loop)
        client._client = httpx.AsyncClient(transport=AsyncMockTransport(), timeout=5.0)
        client._sem = asyncio.Semaphore(2)
        client._active = 0
    await _patch()

    results = await asyncio.gather(*[
        client.generate(f"p{i}", model="m") for i in range(5)
    ])
    assert len(results) == 5
    assert inflight["max"] <= 2


def test_cosine_similarity_identical_vectors():
    assert EmbeddingService.cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    assert EmbeddingService.cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)


def test_cosine_similarity_safe_on_zero_vector():
    assert EmbeddingService.cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


def test_cosine_similarity_safe_on_mismatched_length():
    assert EmbeddingService.cosine_similarity([1, 2], [1, 2, 3]) == 0.0


async def test_embedding_service_returns_none_on_llm_error():
    async def handler(_request):
        raise httpx.ConnectError("down")

    class AsyncMockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await handler(request)

    raw_client = OllamaClient(base_url="http://ollama.test", timeout=2.0, max_concurrent=1)
    loop = asyncio.get_running_loop()
    raw_client._loop_id = id(loop)
    raw_client._client = httpx.AsyncClient(transport=AsyncMockTransport(), timeout=2.0)
    raw_client._sem = asyncio.Semaphore(1)
    raw_client._active = 0

    svc = EmbeddingService(client=raw_client)
    assert await svc.embed("hi", model="emb") is None
