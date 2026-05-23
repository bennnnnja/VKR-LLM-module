from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import redis as sync_redis
import redis.asyncio as async_redis

from app.config import settings
from app.schemas.job import Job, JobError, JobStatus, LLMLog

JOB_KEY_PREFIX = "job:"
CANCEL_FLAG_PREFIX = "cancel:"


def _key(job_id: str) -> str:
    return f"{JOB_KEY_PREFIX}{job_id}"


def _cancel_key(job_id: str) -> str:
    return f"{CANCEL_FLAG_PREFIX}{job_id}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStoreAsync:
    """Асинхронный CRUD по Job для FastAPI-роутеров."""

    def __init__(self, redis_url: str | None = None, ttl_seconds: int | None = None) -> None:
        self._redis = async_redis.from_url(
            redis_url or settings.redis.redis_url,
            decode_responses=True,
        )
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.redis.job_ttl_seconds

    async def close(self) -> None:
        await self._redis.aclose()

    async def create(self, job: Job) -> None:
        await self._redis.set(_key(job.job_id), job.model_dump_json(), ex=self._ttl)

    async def get(self, job_id: str) -> Optional[Job]:
        raw = await self._redis.get(_key(job_id))
        if raw is None:
            return None
        return Job.model_validate_json(raw)

    async def _save(self, job: Job) -> None:
        job.touch()
        await self._redis.set(_key(job.job_id), job.model_dump_json(), ex=self._ttl)

    async def update_status(self, job_id: str, status: JobStatus) -> Optional[Job]:
        job = await self.get(job_id)
        if job is None:
            return None
        job.status = status
        await self._save(job)
        return job

    async def set_started(self, job_id: str) -> None:
        job = await self.get(job_id)
        if job is None:
            return
        job.status = JobStatus.in_progress
        job.started_at = _utcnow_iso()
        await self._save(job)

    async def set_finished(self, job_id: str, status: JobStatus = JobStatus.completed) -> None:
        job = await self.get(job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = _utcnow_iso()
        await self._save(job)

    async def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        job = await self.get(job_id)
        if job is None:
            return
        job.result = result
        await self._save(job)

    async def set_error(self, job_id: str, error: JobError) -> None:
        job = await self.get(job_id)
        if job is None:
            return
        job.error = error
        await self._save(job)

    async def set_llm_log(self, job_id: str, llm_log: LLMLog) -> None:
        job = await self.get(job_id)
        if job is None:
            return
        job.llm_log = llm_log
        await self._save(job)

    async def set_cancellation_requested(self, job_id: str) -> None:
        await self._redis.set(_cancel_key(job_id), "1", ex=self._ttl)

    async def is_cancellation_requested(self, job_id: str) -> bool:
        return bool(await self._redis.exists(_cancel_key(job_id)))

    async def delete(self, job_id: str) -> None:
        await self._redis.delete(_key(job_id), _cancel_key(job_id))


class JobStoreSync:
    """Синхронная версия для Celery-тасков."""

    def __init__(self, redis_url: str | None = None, ttl_seconds: int | None = None) -> None:
        self._redis = sync_redis.from_url(
            redis_url or settings.redis.redis_url,
            decode_responses=True,
        )
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.redis.job_ttl_seconds

    def get(self, job_id: str) -> Optional[Job]:
        raw = self._redis.get(_key(job_id))
        if raw is None:
            return None
        return Job.model_validate_json(raw)

    def _save(self, job: Job) -> None:
        job.touch()
        self._redis.set(_key(job.job_id), job.model_dump_json(), ex=self._ttl)

    def update_status(self, job_id: str, status: JobStatus) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        job.status = status
        self._save(job)
        return job

    def set_started(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.status = JobStatus.in_progress
        job.started_at = _utcnow_iso()
        self._save(job)

    def set_finished(self, job_id: str, status: JobStatus = JobStatus.completed) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = _utcnow_iso()
        self._save(job)

    def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.result = result
        self._save(job)

    def set_error(self, job_id: str, error: JobError) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.error = error
        self._save(job)

    def set_llm_log(self, job_id: str, llm_log: LLMLog) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.llm_log = llm_log
        self._save(job)

    def is_cancellation_requested(self, job_id: str) -> bool:
        return bool(self._redis.exists(_cancel_key(job_id)))

    def clear_cancellation(self, job_id: str) -> None:
        self._redis.delete(_cancel_key(job_id))
