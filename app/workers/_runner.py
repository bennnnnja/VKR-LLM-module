from __future__ import annotations

import time
from typing import Any, Callable

from loguru import logger

from app.schemas.job import JobError, JobStatus, LLMLog
from app.services.job_store import JobStoreSync
from app.services.model_router import ModelRouter, ResolutionMode


def _cancelled(store: JobStoreSync, job_id: str) -> bool:
    return store.is_cancellation_requested(job_id)


def run_job(
    job_id: str,
    target_model: str,
    direct_payload: Callable[[], dict[str, Any]],
    stub_payload: Callable[[], dict[str, Any]],
) -> None:
    """Общий каркас Celery-задачи фазы 1.

    direct_payload — что возвращать при mode in {"direct","fallback"}
                     (на фазе 1 это mock; в фазах 3-4 — реальный вызов LLM).
    stub_payload   — что возвращать при mode=="stub".
    """
    store = JobStoreSync()

    job = store.get(job_id)
    if job is None:
        logger.warning("job {} not found in store, skipping", job_id)
        return

    if _cancelled(store, job_id):
        store.set_finished(job_id, status=JobStatus.cancelled)
        logger.info("job {} cancelled before start", job_id)
        return

    store.set_started(job_id)

    router = ModelRouter()
    actual_model, mode = router.resolve(target_model)
    logger.info("Target model: {}, resolution: {}", target_model, mode)
    if mode == "fallback":
        logger.info("Fallback active → physically calling {}", actual_model)

    if mode == "fail":
        store.set_llm_log(
            job_id,
            LLMLog(
                target_model=target_model,
                actual_model=actual_model,
                model_resolution=mode,
            ),
        )
        store.set_error(
            job_id,
            JobError(
                code="model_unavailable",
                message=(
                    f"target model {target_model!r} is not available "
                    f"and strategy=fail blocks fallback"
                ),
            ),
        )
        store.set_finished(job_id, status=JobStatus.failed)
        return

    started = time.monotonic()

    if mode == "stub":
        time.sleep(1)
    else:
        time.sleep(3)

    if _cancelled(store, job_id):
        store.set_finished(job_id, status=JobStatus.cancelled)
        logger.info("job {} cancelled mid-flight", job_id)
        return

    duration_ms = int((time.monotonic() - started) * 1000)

    result = stub_payload() if mode == "stub" else direct_payload()

    store.set_llm_log(
        job_id,
        LLMLog(
            target_model=target_model,
            actual_model=actual_model,
            model_resolution=mode,
            prompt="<stub: prompt will be filled in phase 3>",
            raw_response="<stub: raw response will be filled in phase 3>",
            duration_ms=duration_ms,
            retries=0,
        ),
    )
    store.set_result(job_id, result)
    store.set_finished(job_id, status=JobStatus.completed)
    logger.info("Stub completed in {}ms", duration_ms)


__all__ = ["run_job", "ResolutionMode"]
