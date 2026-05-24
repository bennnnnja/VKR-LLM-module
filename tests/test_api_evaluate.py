from __future__ import annotations

import pytest

from app.workers import _runner as runner_module
from app.workers.celery_app import celery_app


@pytest.fixture(autouse=True)
def celery_eager(monkeypatch):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    monkeypatch.setattr(runner_module.time, "sleep", lambda _seconds: None)
    yield
    celery_app.conf.task_always_eager = False


def test_evaluate_body_validation(client, api_key):
    # task_text обязателен
    r = client.post(
        "/evaluate/task",
        headers={"X-API-Key": api_key},
        json={"reference_answer": "x", "student_answer": "y"},
    )
    assert r.status_code == 422


def test_recommendations_lifecycle(client, api_key, fake_llm):
    import json
    fake_llm.ollama.push_response(json.dumps({
        "recommendations": [
            {"text": "Вариант 1", "rationale": "r1", "confidence": 0.9},
            {"text": "Вариант 2", "rationale": "r2", "confidence": 0.8},
        ]
    }))
    r = client.post(
        "/generate/recommendations",
        headers={"X-API-Key": api_key},
        json={"task_description": "Опиши SRP", "max_recommendations": 2},
    )
    assert r.status_code == 202
    job_id = r.json()["jobId"]

    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    body = r.json()
    assert body["status"] == "completed"
    assert body["llm_log"]["model_resolution"] == "direct"
    assert body["job_type"] == "recommendations"
    assert len(body["result"]["recommendations"]) == 2


def test_recommendations_rejects_old_shape(client, api_key):
    """Старая форма {task_text, student_answer} больше не валидна."""
    r = client.post(
        "/generate/recommendations",
        headers={"X-API-Key": api_key},
        json={"task_text": "t", "student_answer": "s"},
    )
    assert r.status_code == 422


def test_discipline_test_stub(client, api_key):
    r = client.post(
        "/analyze/test-discipline",
        headers={"X-API-Key": api_key},
        json={"test_text": "Задача про связные списки и хеш-таблицы"},
    )
    assert r.status_code == 202
    job_id = r.json()["jobId"]
    body = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key}).json()
    # qwen3:8b недоступна, strategy=stub
    assert body["status"] == "completed"
    assert body["llm_log"]["target_model"] == "qwen3:8b"
    assert body["llm_log"]["model_resolution"] == "stub"
