from __future__ import annotations

from app.config import settings
from app.workers._runner import run_job
from app.workers.celery_app import celery_app


def _direct_payload() -> dict:
    return {
        "items": [
            {
                "title": "Mock-рекомендация",
                "detail": "Mock-результат фазы 1. Реальный вызов LLM появится в фазе 3.",
                "priority": 1,
            }
        ],
        "summary": "mock summary",
    }


def _stub_payload() -> dict:
    return {
        "items": [],
        "summary": "STUB: модель недоступна, возвращён пустой список рекомендаций.",
        "note": "stub-resolution",
    }


@celery_app.task(name="app.workers.recommendations_task.recommendations_task")
def recommendations_task(job_id: str) -> None:
    run_job(
        job_id=job_id,
        target_model=settings.models.model_recommendations,
        direct_payload=_direct_payload,
        stub_payload=_stub_payload,
    )
