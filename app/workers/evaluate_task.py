from __future__ import annotations

import asyncio
import time

from loguru import logger
from pydantic import ValidationError

from app import deps
from app.config import settings
from app.schemas.job import JobError, JobStatus, LLMLog
from app.schemas.llm_outputs import EvaluateLLMOutput
from app.services.embedding_service import EmbeddingService
from app.services.job_store import JobStoreSync
from app.services.llm_client import LLMTimeout, LLMUnavailable
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder
from app.workers._async_bridge import run_async
from app.workers.celery_app import celery_app


def _stub_result() -> dict:
    return {
        "total_score": 0,
        "criteria": [
            {"name": "Точность",     "score": 0, "comment": "stub"},
            {"name": "Полнота",      "score": 0, "comment": "stub"},
            {"name": "Логика",       "score": 0, "comment": "stub"},
            {"name": "Терминология", "score": 0, "comment": "stub"},
        ],
        "summary": "STUB: модель оценки недоступна, реальная оценка не произведена.",
        "strengths": [],
        "weaknesses": [],
        "note": "stub-resolution",
    }


@celery_app.task(name="app.workers.evaluate_task.evaluate_task")
def evaluate_task(job_id: str) -> None:
    run_async(_run, job_id)


async def _run(job_id: str) -> None:
    from app.services.job_store import JobStoreAsync

    store = JobStoreAsync()
    try:
        await _evaluate(store, job_id)
    finally:
        await store.close()


async def _evaluate(store, job_id: str) -> None:
    job = await store.get(job_id)
    if job is None:
        logger.warning("evaluate_task: job {} not found", job_id)
        return

    if await store.is_cancellation_requested(job_id):
        await store.set_finished(job_id, status=JobStatus.cancelled)
        return

    await store.set_started(job_id)

    target_model = settings.models.model_evaluate
    actual_model, mode = ModelRouter().resolve(target_model)
    logger.info(
        "evaluate_task: job={} target={} actual={} mode={}",
        job_id, target_model, actual_model, mode,
    )

    if mode == "fail":
        await _finalize_failed(
            store, job_id, target_model, actual_model, mode,
            code="model_unavailable",
            message=f"target model {target_model!r} is not available and strategy=fail",
            prompt="",
        )
        return

    if mode == "stub":
        await asyncio.sleep(1)
        if await store.is_cancellation_requested(job_id):
            await store.set_finished(job_id, status=JobStatus.cancelled)
            return
        await store.set_llm_log(job_id, LLMLog(
            target_model=target_model,
            actual_model=actual_model,
            model_resolution=mode,
            duration_ms=1000,
        ))
        await store.set_result(job_id, _stub_result())
        await store.set_finished(job_id, status=JobStatus.completed)
        return

    # mode in ("direct", "fallback") — реальный вызов LLM
    payload = job.input_data
    builder = PromptBuilder()
    prompt = builder.build_evaluate(
        task_description=payload.get("task_text", ""),
        reference_answer=payload.get("reference_answer", ""),
        student_answer=payload.get("student_answer", ""),
        discipline=payload.get("discipline"),
        rubric=payload.get("rubric"),
    )

    if await store.is_cancellation_requested(job_id):
        await store.set_finished(job_id, status=JobStatus.cancelled)
        return

    client = deps.get_ollama_client()
    total_duration_ms = 0
    retries = 0
    raw_response = ""
    parsed: EvaluateLLMOutput | None = None

    try:
        raw_response, meta = await client.generate(
            prompt, model=actual_model, format="json"
        )
        total_duration_ms += meta.duration_ms
        try:
            parsed = EvaluateLLMOutput.model_validate_json(raw_response)
        except ValidationError as ve:
            retries = 1
            logger.warning("evaluate_task: invalid JSON on attempt 1, retrying. err={}", ve)
            if await store.is_cancellation_requested(job_id):
                await store.set_finished(job_id, status=JobStatus.cancelled)
                return

            retry_prompt = builder.build_evaluate_retry(prompt, raw_response, str(ve))
            raw_response, meta2 = await client.generate(
                retry_prompt, model=actual_model, format="json"
            )
            total_duration_ms += meta2.duration_ms
            try:
                parsed = EvaluateLLMOutput.model_validate_json(raw_response)
            except ValidationError as ve2:
                await store.set_llm_log(job_id, LLMLog(
                    target_model=target_model,
                    actual_model=actual_model,
                    model_resolution=mode,
                    prompt=prompt,
                    raw_response=raw_response,
                    duration_ms=total_duration_ms,
                    retries=retries,
                ))
                await store.set_error(job_id, JobError(
                    code="llm_invalid_output",
                    message=str(ve2)[:500],
                ))
                await store.set_finished(job_id, status=JobStatus.failed)
                return

    except LLMTimeout as exc:
        await _finalize_failed(
            store, job_id, target_model, actual_model, mode,
            code="llm_timeout", message=str(exc)[:500], prompt=prompt,
        )
        return
    except LLMUnavailable as exc:
        await _finalize_failed(
            store, job_id, target_model, actual_model, mode,
            code="llm_unavailable", message=str(exc)[:500], prompt=prompt,
        )
        return

    assert parsed is not None

    if await store.is_cancellation_requested(job_id):
        await store.set_finished(job_id, status=JobStatus.cancelled)
        return

    # Опциональная постобработка: косинусная близость через эмбеддер.
    # Если эмбеддер недоступен — секция similarity просто отсутствует.
    similarity = await _maybe_similarity(
        payload.get("reference_answer", ""),
        payload.get("student_answer", ""),
    )

    result = parsed.model_dump(exclude_none=True)
    if similarity is not None:
        result["similarity"] = similarity

    # scaled_score — если клиент попросил шкалу не 100
    max_score = float(payload.get("max_score") or 100.0)
    if 0.0 < max_score < 100.0 or max_score > 100.0:
        result["scaled_score"] = round(parsed.total_score / 100.0 * max_score, 2)
        result["scaled_max"] = max_score

    await store.set_llm_log(job_id, LLMLog(
        target_model=target_model,
        actual_model=actual_model,
        model_resolution=mode,
        prompt=prompt,
        raw_response=raw_response,
        duration_ms=total_duration_ms,
        retries=retries,
    ))
    await store.set_result(job_id, result)
    await store.set_finished(job_id, status=JobStatus.completed)


async def _maybe_similarity(reference: str, student: str) -> float | None:
    if not reference or not student:
        return None
    try:
        svc = deps.get_embedding_service()
        ref_emb = await svc.embed(reference, model=settings.models.model_embedding)
        stu_emb = await svc.embed(student, model=settings.models.model_embedding)
        if ref_emb is None or stu_emb is None:
            return None
        return round(EmbeddingService.cosine_similarity(ref_emb, stu_emb), 4)
    except Exception as exc:  # noqa: BLE001
        logger.warning("similarity post-process failed: {}", exc)
        return None


async def _finalize_failed(
    store,
    job_id: str,
    target_model: str,
    actual_model: str,
    mode: str,
    code: str,
    message: str,
    prompt: str,
) -> None:
    await store.set_llm_log(job_id, LLMLog(
        target_model=target_model,
        actual_model=actual_model,
        model_resolution=mode,
        prompt=prompt,
    ))
    await store.set_error(job_id, JobError(code=code, message=message))
    await store.set_finished(job_id, status=JobStatus.failed)
