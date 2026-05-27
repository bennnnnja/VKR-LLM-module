from __future__ import annotations

import pytest

from app.workers import _runner as runner_module
from app.workers.celery_app import celery_app


@pytest.fixture(autouse=True)
def celery_eager(monkeypatch):
    """Запускаем таски синхронно прямо в тестах, без отдельного воркера и брокера."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    # Сделаем sleep мгновенным
    monkeypatch.setattr(runner_module.time, "sleep", lambda _seconds: None)
    yield
    celery_app.conf.task_always_eager = False


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_evaluate_requires_api_key(client):
    r = client.post(
        "/evaluate/task",
        json={
            "task_text": "t",
            "reference_answer": "r",
            "student_answer": "s",
        },
    )
    assert r.status_code == 401


def test_evaluate_full_lifecycle_direct(client, api_key):
    # qwen2.5:32b-instruct доступна → mode=direct
    r = client.post(
        "/evaluate/task",
        headers={"X-API-Key": api_key},
        json={
            "task_text": "Что такое полиморфизм?",
            "reference_answer": "Полиморфизм — это...",
            "student_answer": "Полиморфизм это когда...",
        },
    )
    assert r.status_code == 202
    job_id = r.json()["jobId"]

    # Eager-mode: к этому моменту таск уже отработал
    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["result"] is not None
    assert body["llm_log"]["target_model"] == "qwen2.5:32b-instruct"
    assert body["llm_log"]["actual_model"] == "qwen2.5:32b-instruct"
    assert body["llm_log"]["model_resolution"] == "direct"
    assert body["started_at"] is not None
    assert body["finished_at"] is not None


def test_testcases_stub_resolution(client, api_key):
    # qwen3-coder-next НЕдоступна, strategy=stub → mode=stub
    r = client.post(
        "/generate/testcases",
        headers={"X-API-Key": api_key},
        json={"task_description": "Сложить два числа", "language": "python", "count": 3},
    )
    assert r.status_code == 202
    job_id = r.json()["jobId"]

    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["llm_log"]["target_model"] == "qwen3-coder-next"
    assert body["llm_log"]["model_resolution"] == "stub"
    assert body["result"]["cases"] == []
    assert "STUB" in body["result"]["note"]


def test_get_job_404(client, api_key):
    r = client.get("/jobs/does-not-exist", headers={"X-API-Key": api_key})
    assert r.status_code == 404


def test_cancel_completed_returns_409(client, api_key):
    r = client.post(
        "/evaluate/task",
        headers={"X-API-Key": api_key},
        json={"task_text": "x", "reference_answer": "y", "student_answer": "z"},
    )
    job_id = r.json()["jobId"]

    # Уже completed (eager)
    r = client.post(f"/jobs/{job_id}/cancel", headers={"X-API-Key": api_key})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "job_not_cancellable"


def test_analyze_task_discipline_sync_stub(client, api_key):
    """В дефолтном тестовом окружении qwen3:8b не в available_models,
    поэтому sync-эндпоинт уходит в stub-ветку и возвращает Прочее/0.0
    без вызова LLM. Реальный direct-путь покрыт в test_discipline_phase6."""
    r = client.post(
        "/analyze/task-discipline",
        headers={"X-API-Key": api_key},
        json={"task_text": "Написать сортировку пузырьком"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["discipline"] == "Прочее"
    assert body["confidence"] == 0.0


def test_cancel_pending_job(client, api_key):
    """pending → cancelled. Создаём job напрямую в сторадже, не дёргая брокер."""
    import asyncio

    from app.schemas.job import Job, JobType
    from app.services.job_store import JobStoreAsync

    async def _create_pending() -> str:
        store = JobStoreAsync()
        try:
            job = Job(job_type=JobType.evaluate, input_data={"task_text": "x"})
            await store.create(job)
            return job.job_id
        finally:
            await store.close()

    job_id = asyncio.get_event_loop().run_until_complete(_create_pending()) \
        if False else asyncio.run(_create_pending())

    # Прежде чем дёргать cancel, отключим попытки celery revoke до реального брокера —
    # просто заменим control.revoke на no-op.
    from app.workers.celery_app import celery_app as ca

    class _NoopControl:
        def revoke(self, *_a, **_kw):
            return None

    ca.control = _NoopControl()  # type: ignore[assignment]

    r = client.post(f"/jobs/{job_id}/cancel", headers={"X-API-Key": api_key})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert r.json()["status"] == "cancelled"
