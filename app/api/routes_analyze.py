from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import ValidationError

from app import deps
from app.config import settings
from app.schemas.discipline import (
    DISCIPLINES,
    DisciplineResponse,
    DisciplineTaskRequest,
)
from app.schemas.llm_outputs import DisciplineLLMOutput
from app.services.llm_client import LLMTimeout, LLMUnavailable
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post(
    "/task-discipline",
    status_code=status.HTTP_200_OK,
    response_model=DisciplineResponse,
)
async def post_task_discipline(payload: DisciplineTaskRequest) -> DisciplineResponse:
    """Синхронный эндпоинт классификации дисциплины — без Celery, без JobStore.

    Жёсткий таймаут SYNC_LLM_TIMEOUT_SECONDS (default 30s) — клиент держит
    HTTP-соединение открытым всё время вызова LLM, поэтому ограничение
    строже общего LLM_TIMEOUT_SECONDS.

    При недоступности модели или невалидном ответе после retry — HTTP-ошибки
    (502 / 504 / 503), а не Job со статусом failed (нет JobStore).
    """
    target_model = settings.models.model_discipline
    actual_model, mode = ModelRouter().resolve(target_model)

    logger.info("[sync task-discipline] Target model: {}, resolution: {}", target_model, mode)

    if mode == "fail":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "model_unavailable",
                "message": f"target model {target_model!r} is not available and strategy=fail",
            },
        )

    if mode == "stub":
        # Когда модель не объявлена доступной — отдаём "Прочее"/0.0 без выдумок.
        return DisciplineResponse(discipline="Прочее", confidence=0.0)

    # mode in ("direct", "fallback")
    prompt = PromptBuilder().build_discipline(text=payload.task_text, kind="задание")

    # Используем общий singleton OllamaClient (общий semaphore с async-путями),
    # но переопределяем timeout на конкретный вызов — синхронный эндпоинт
    # не должен держать HTTP-соединение клиента дольше 30 сек.
    client = deps.get_ollama_client()
    sync_timeout = settings.ollama.sync_llm_timeout_seconds

    try:
        raw, _meta = await client.generate(
            prompt, model=actual_model, format="json", timeout=sync_timeout,
        )
    except LLMTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "llm_timeout", "message": str(exc)[:500]},
        ) from exc
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "llm_unavailable", "message": str(exc)[:500]},
        ) from exc

    try:
        parsed = DisciplineLLMOutput.model_validate_json(raw)
    except ValidationError as ve:
        # Один retry с уточнением — тот же лимит 30 сек на каждый вызов.
        retry_prompt = PromptBuilder().build_retry(prompt, raw, str(ve))
        try:
            raw2, _ = await client.generate(
                retry_prompt, model=actual_model, format="json", timeout=sync_timeout,
            )
            parsed = DisciplineLLMOutput.model_validate_json(raw2)
        except LLMTimeout as exc:
            raise HTTPException(
                status_code=504,
                detail={"code": "llm_timeout", "message": str(exc)[:500]},
            ) from exc
        except LLMUnavailable as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "llm_unavailable", "message": str(exc)[:500]},
            ) from exc
        except ValidationError as ve2:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "llm_invalid_output",
                    "message": (
                        f"LLM вернула невалидный JSON даже после retry: {str(ve2)[:300]}. "
                        f"Допустимые значения discipline: {', '.join(DISCIPLINES)}"
                    ),
                },
            ) from ve2

    return DisciplineResponse(discipline=parsed.discipline, confidence=parsed.confidence)
