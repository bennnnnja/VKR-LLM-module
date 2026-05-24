from __future__ import annotations

from loguru import logger
from pydantic import BaseModel

from app import deps
from app.config import settings
from app.schemas.llm_outputs import EvaluateLLMOutput
from app.services.embedding_service import EmbeddingService
from app.services.prompt_builder import PromptBuilder
from app.workers._async_bridge import run_async
from app.workers._llm_runner import run_llm_task
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


def _build_prompt(payload: dict) -> str:
    return PromptBuilder().build_evaluate(
        task_description=payload.get("task_text", ""),
        reference_answer=payload.get("reference_answer", ""),
        student_answer=payload.get("student_answer", ""),
        discipline=payload.get("discipline"),
        rubric=payload.get("rubric"),
    )


async def _postprocess(result_dict: dict, parsed: BaseModel, payload: dict) -> None:
    # similarity через embedder (best-effort)
    similarity = await _maybe_similarity(
        payload.get("reference_answer", ""),
        payload.get("student_answer", ""),
    )
    if similarity is not None:
        result_dict["similarity"] = similarity

    # scaled_score, если клиент попросил шкалу не 100
    assert isinstance(parsed, EvaluateLLMOutput)
    max_score = float(payload.get("max_score") or 100.0)
    if max_score != 100.0:
        result_dict["scaled_score"] = round(parsed.total_score / 100.0 * max_score, 2)
        result_dict["scaled_max"] = max_score


async def _maybe_similarity(reference: str, student: str) -> float | None:
    if not reference or not student:
        return None
    try:
        svc = deps.get_embedding_service()
        emb_model = settings.models.model_embedding
        logger.info("Computing similarity via {}", emb_model)
        ref_emb = await svc.embed(reference, model=emb_model)
        stu_emb = await svc.embed(student, model=emb_model)
        if ref_emb is None or stu_emb is None:
            logger.info("Similarity skipped (embedder unavailable)")
            return None
        sim = round(EmbeddingService.cosine_similarity(ref_emb, stu_emb), 4)
        logger.info("Similarity = {}", sim)
        return sim
    except Exception as exc:  # noqa: BLE001
        logger.warning("similarity post-process failed: {}", exc)
        return None


@celery_app.task(name="app.workers.evaluate_task.evaluate_task")
def evaluate_task(job_id: str) -> None:
    run_async(
        run_llm_task,
        job_id=job_id,
        target_model=settings.models.model_evaluate,
        build_prompt=_build_prompt,
        output_schema=EvaluateLLMOutput,
        stub_result=_stub_result(),
        postprocess=_postprocess,
        log_label="evaluate_task",
    )
