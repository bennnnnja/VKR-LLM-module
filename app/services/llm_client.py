from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from app.config import settings


class LLMError(Exception):
    """Базовый класс LLM-ошибок."""


class LLMTimeout(LLMError):
    """Ollama не ответила в течение LLM_TIMEOUT_SECONDS."""


class LLMUnavailable(LLMError):
    """Ollama не доступна (сетевая ошибка, 4xx/5xx, прокси заблокировал)."""


@dataclass
class GenerateMeta:
    duration_ms: int
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    total_duration_ns: int | None = None


class OllamaClient:
    """Асинхронный HTTP-клиент к Ollama с глобальным concurrency-лимитом.

    Сценарии использования:
        - FastAPI: один singleton на процесс, живёт всё время приложения
          (создаётся в app.deps). Семафор и httpx.AsyncClient привязаны к
          единственному циклу событий FastAPI и переиспользуются.
        - Celery: тот же singleton, но Celery-таск делает asyncio.run() —
          каждый вызов получает свой event loop. Семафор и httpx-клиент
          пересоздаются при смене loop'а (см. _get_loop_state).

    Это даёт «не более LLM_MAX_CONCURRENT одновременных физических вызовов
    к Ollama внутри процесса». Между процессами Celery-воркера ограничение
    держится через worker_concurrency.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        self._base_url = (base_url or settings.ollama.ollama_base_url).rstrip("/")
        self._timeout = float(timeout if timeout is not None else settings.ollama.llm_timeout_seconds)
        self._max_concurrent = int(
            max_concurrent if max_concurrent is not None else settings.ollama.llm_max_concurrent
        )

        # Per-loop state — пересоздаётся при первом обращении из нового loop.
        self._loop_id: int | None = None
        self._client: httpx.AsyncClient | None = None
        self._sem: asyncio.Semaphore | None = None
        self._active: int = 0  # сколько запросов сейчас в семафоре

    def _get_loop_state(self) -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
        loop = asyncio.get_running_loop()
        if id(loop) != self._loop_id:
            # Старый httpx-клиент привязан к другому циклу, который уже закрыт,
            # поэтому aclose'ить не получится — отпускаем (GC соберёт).
            self._loop_id = id(loop)
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._sem = asyncio.Semaphore(self._max_concurrent)
            self._active = 0
        assert self._client is not None and self._sem is not None
        return self._client, self._sem

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("OllamaClient.aclose() failed: {}", exc)
            self._client = None
            self._loop_id = None

    async def generate(
        self,
        prompt: str,
        model: str,
        format: str | None = "json",
        options: dict[str, Any] | None = None,
    ) -> tuple[str, GenerateMeta]:
        """Вызов /api/generate. Возвращает (raw_text, metadata)."""
        client, sem = self._get_loop_state()
        url = f"{self._base_url}/api/generate"
        body: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if format:
            body["format"] = format
        if options:
            body["options"] = options

        logger.info(
            "Calling Ollama (model={}, prompt={}b, in-flight={}/{})",
            model,
            len(prompt),
            self._active,
            self._max_concurrent,
        )

        async with sem:
            self._active += 1
            start = time.monotonic()
            try:
                try:
                    response = await client.post(url, json=body)
                except httpx.TimeoutException as exc:
                    raise LLMTimeout(
                        f"Ollama timeout after {self._timeout}s on model {model!r}"
                    ) from exc
                except (
                    httpx.ConnectError,
                    httpx.ConnectTimeout,
                    httpx.ReadError,
                    httpx.NetworkError,
                ) as exc:
                    raise LLMUnavailable(
                        f"Ollama not reachable at {self._base_url}: {exc}"
                    ) from exc

                duration_ms = int((time.monotonic() - start) * 1000)

                if response.status_code >= 500:
                    raise LLMUnavailable(
                        f"Ollama HTTP {response.status_code}: {response.text[:200]}"
                    )
                if response.status_code >= 400:
                    # 4xx — обычно проблема в нашем запросе. Считаем «недоступно по факту».
                    raise LLMUnavailable(
                        f"Ollama HTTP {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                raw_text = data.get("response", "")
                meta = GenerateMeta(
                    duration_ms=duration_ms,
                    eval_count=data.get("eval_count"),
                    prompt_eval_count=data.get("prompt_eval_count"),
                    total_duration_ns=data.get("total_duration"),
                )
                logger.info(
                    "Generation took {:.1f}s, {} tokens",
                    duration_ms / 1000.0,
                    meta.eval_count or 0,
                )
                return raw_text, meta
            finally:
                self._active -= 1

    async def embeddings(self, prompt: str, model: str) -> list[float]:
        """Вызов /api/embeddings. Возвращает вектор."""
        client, sem = self._get_loop_state()
        url = f"{self._base_url}/api/embeddings"
        body = {"model": model, "prompt": prompt}

        async with sem:
            self._active += 1
            try:
                try:
                    response = await client.post(url, json=body)
                except httpx.TimeoutException as exc:
                    raise LLMTimeout(
                        f"Ollama embeddings timeout after {self._timeout}s"
                    ) from exc
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as exc:
                    raise LLMUnavailable(
                        f"Ollama not reachable at {self._base_url}: {exc}"
                    ) from exc

                if response.status_code >= 400:
                    raise LLMUnavailable(
                        f"Ollama embeddings HTTP {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                emb = data.get("embedding")
                if not isinstance(emb, list):
                    raise LLMUnavailable("Ollama embeddings: malformed response")
                return [float(x) for x in emb]
            finally:
                self._active -= 1
