from __future__ import annotations

from app.config import settings
from app.schemas.llm_outputs import RecommendationsLLMOutput
from app.services.prompt_builder import PromptBuilder
from app.workers._async_bridge import run_async
from app.workers._llm_runner import run_llm_task
from app.workers.celery_app import celery_app


def _stub_result() -> dict:
    return {
        "recommendations": [
            {
                "text": "STUB: модель рекомендаций недоступна.",
                "rationale": "stub-resolution",
                "confidence": 0.0,
            }
        ],
        "note": "stub-resolution",
    }


def _build_prompt(payload: dict) -> str:
    return PromptBuilder().build_recommendations(
        task_description=payload.get("task_description", ""),
        n=int(payload.get("max_recommendations") or 5),
        discipline=payload.get("discipline"),
        user_prompt=payload.get("user_prompt"),
    )


@celery_app.task(name="app.workers.recommendations_task.recommendations_task")
def recommendations_task(job_id: str) -> None:
    run_async(
        run_llm_task,
        job_id=job_id,
        target_model=settings.models.model_recommendations,
        build_prompt=_build_prompt,
        output_schema=RecommendationsLLMOutput,
        stub_result=_stub_result(),
        log_label="recommendations_task",
    )
