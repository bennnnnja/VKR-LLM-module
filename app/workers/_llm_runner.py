from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Type

from loguru import logger
from pydantic import BaseModel, ValidationError

from app import deps
from app.schemas.job import JobError, JobStatus, LLMLog
from app.services.job_store import JobStoreAsync
from app.services.llm_client import LLMTimeout, LLMUnavailable
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder


# Тип postprocess: (result_dict, parsed_output, input_data) → могут мутировать result_dict.
Postprocess = Callable[[dict, BaseModel, dict[str, Any]], Awaitable[None]]


async def run_llm_task(
    *,
    job_id: str,
    target_model: str,
    build_prompt: Callable[[dict[str, Any]], str],
    output_schema: Type[BaseModel],
    stub_result: dict,
    postprocess: Postprocess | None = None,
    log_label: str = "llm_task",
) -> None:
    """Общий async-каркас для тасок «вызвать LLM, провалидировать, сохранить».

    Шаги:
      1. Загрузить Job из стора, проверить отмену.
      2. set_started.
      3. Через ModelRouter определить (actual_model, mode).
      4. mode=fail   → failed/model_unavailable.
      5. mode=stub   → задержка 1с, фиксированный stub_result, completed.
      6. mode=direct/fallback:
         a. build_prompt → реальный вызов LLM (1 retry на ValidationError).
         b. ValidationError × 2 → failed/llm_invalid_output.
         c. LLMTimeout → failed/llm_timeout.
         d. LLMUnavailable → failed/llm_unavailable.
         e. parsed.model_dump() + опциональный postprocess → result, completed.
      7. На каждом шаге — повторная проверка cancellation_requested.
    """
    store = JobStoreAsync()
    try:
        await _execute(
            store=store,
            job_id=job_id,
            target_model=target_model,
            build_prompt=build_prompt,
            output_schema=output_schema,
            stub_result=stub_result,
            postprocess=postprocess,
            log_label=log_label,
        )
    finally:
        await store.close()


async def _execute(
    *,
    store: JobStoreAsync,
    job_id: str,
    target_model: str,
    build_prompt: Callable[[dict[str, Any]], str],
    output_schema: Type[BaseModel],
    stub_result: dict,
    postprocess: Postprocess | None,
    log_label: str,
) -> None:
    job = await store.get(job_id)
    if job is None:
        logger.warning("{}: job {} not found", log_label, job_id)
        return

    if await store.is_cancellation_requested(job_id):
        await store.set_finished(job_id, status=JobStatus.cancelled)
        return

    await store.set_started(job_id)

    actual_model, mode = ModelRouter().resolve(target_model)
    logger.info("Target model: {}, resolution: {}", target_model, mode)
    if mode == "fallback":
        logger.info("Fallback active → physically calling {}", actual_model)

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
        await store.set_result(job_id, stub_result)
        await store.set_finished(job_id, status=JobStatus.completed)
        return

    # mode in ("direct", "fallback") — реальный вызов LLM
    payload = job.input_data
    builder = PromptBuilder()
    prompt = build_prompt(payload)

    if await store.is_cancellation_requested(job_id):
        await store.set_finished(job_id, status=JobStatus.cancelled)
        return

    client = deps.get_ollama_client()
    raw_response = ""
    total_duration_ms = 0
    retries = 0
    parsed: BaseModel | None = None

    try:
        raw_response, meta = await client.generate(
            prompt, model=actual_model, format="json"
        )
        total_duration_ms += meta.duration_ms
        try:
            parsed = output_schema.model_validate_json(raw_response)
        except ValidationError as ve:
            retries = 1
            logger.warning("{}: invalid JSON on attempt 1, retrying. err={}", log_label, ve)
            if await store.is_cancellation_requested(job_id):
                await store.set_finished(job_id, status=JobStatus.cancelled)
                return

            retry_prompt = builder.build_retry(prompt, raw_response, str(ve))
            raw_response, meta2 = await client.generate(
                retry_prompt, model=actual_model, format="json"
            )
            total_duration_ms += meta2.duration_ms
            try:
                parsed = output_schema.model_validate_json(raw_response)
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

    result = parsed.model_dump(exclude_none=True)
    if postprocess is not None:
        try:
            await postprocess(result, parsed, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("{}: postprocess failed: {}", log_label, exc)

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


async def _finalize_failed(
    store: JobStoreAsync,
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
