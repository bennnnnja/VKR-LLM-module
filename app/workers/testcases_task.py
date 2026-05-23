from __future__ import annotations

from app.config import settings
from app.workers._runner import run_job
from app.workers.celery_app import celery_app


def _direct_payload() -> dict:
    return {
        "cases": [
            {
                "name": "mock_basic",
                "input": "1 2",
                "expected_output": "3",
                "is_edge_case": False,
            }
        ],
        "note": "Mock-результат фазы 1. Реальный вызов qwen3-coder-next появится в фазе 3.",
    }


def _stub_payload() -> dict:
    return {
        "cases": [],
        "note": "STUB: qwen3-coder-next недоступна, тест-кейсы не сгенерированы.",
    }


@celery_app.task(name="app.workers.testcases_task.testcases_task")
def testcases_task(job_id: str) -> None:
    run_job(
        job_id=job_id,
        target_model=settings.models.model_testcases,
        direct_payload=_direct_payload,
        stub_payload=_stub_payload,
    )
