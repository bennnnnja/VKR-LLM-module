from __future__ import annotations

from app.config import settings
from app.workers._runner import run_job
from app.workers.celery_app import celery_app


def _direct_payload() -> dict:
    return {
        "discipline": "Программирование",
        "confidence": 0.85,
        "note": "Mock-результат фазы 1.",
    }


def _stub_payload() -> dict:
    return {
        "discipline": "unknown",
        "confidence": 0.0,
        "note": "STUB: qwen3:8b недоступна, дисциплина не определена.",
    }


@celery_app.task(name="app.workers.discipline_test_task.discipline_test_task")
def discipline_test_task(job_id: str) -> None:
    run_job(
        job_id=job_id,
        target_model=settings.models.model_discipline,
        direct_payload=_direct_payload,
        stub_payload=_stub_payload,
    )
