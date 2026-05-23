from __future__ import annotations

from app.config import settings
from app.workers._runner import run_job
from app.workers.celery_app import celery_app


def _direct_payload() -> dict:
    return {
        "score": 4.0,
        "max_score": 5.0,
        "rationale": "Mock-результат фазы 1. Реальный вызов LLM появится в фазе 3.",
        "strengths": ["mock strength"],
        "weaknesses": ["mock weakness"],
    }


def _stub_payload() -> dict:
    return {
        "score": 0.0,
        "max_score": 5.0,
        "rationale": "STUB: модель недоступна, возвращён фиксированный шаблон.",
        "strengths": [],
        "weaknesses": [],
        "note": "stub-resolution",
    }


@celery_app.task(name="app.workers.evaluate_task.evaluate_task")
def evaluate_task(job_id: str) -> None:
    run_job(
        job_id=job_id,
        target_model=settings.models.model_evaluate,
        direct_payload=_direct_payload,
        stub_payload=_stub_payload,
    )
