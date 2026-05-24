from __future__ import annotations

import json

import pytest

from app.services.llm_client import GenerateMeta, LLMTimeout, LLMUnavailable
from app.workers.celery_app import celery_app


@pytest.fixture(autouse=True)
def celery_eager():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


VALID_PAYLOAD = {
    "task_description": "Объясните принцип единственной ответственности (SRP) в ООП.",
    "max_recommendations": 5,
    "discipline": "Программирование",
}


def _valid_output(n: int = 5) -> str:
    return json.dumps({
        "recommendations": [
            {
                "text": f"Альтернативный ответ #{i + 1} — корректное определение SRP.",
                "rationale": f"Обоснование для варианта #{i + 1}.",
                "confidence": round(0.95 - i * 0.07, 2),
            }
            for i in range(n)
        ]
    })


def _post(client, api_key, payload=None):
    payload = payload or VALID_PAYLOAD
    r = client.post(
        "/generate/recommendations",
        headers={"X-API-Key": api_key},
        json=payload,
    )
    assert r.status_code == 202, r.text
    return r.json()["jobId"]


def _get(client, api_key, job_id):
    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    return r.json()


# ───────────── базовый успех ─────────────

def test_recommendations_success_default_fake(client, api_key, fake_llm):
    """Default FakeOllamaClient вернёт default eval JSON — не подходит под
    RecommendationsLLMOutput, так что нужно явно проталкивать корректный."""
    fake_llm.ollama.push_response(_valid_output(5))

    job_id = _post(client, api_key)
    job = _get(client, api_key, job_id)

    assert job["status"] == "completed"
    assert job["llm_log"]["target_model"] == "qwen2.5:32b-instruct"
    assert job["llm_log"]["actual_model"] == "qwen2.5:32b-instruct"
    assert job["llm_log"]["model_resolution"] == "direct"
    assert job["llm_log"]["retries"] == 0
    assert job["llm_log"]["prompt"]
    assert job["llm_log"]["raw_response"]
    assert job["llm_log"]["duration_ms"] >= 0

    recs = job["result"]["recommendations"]
    assert len(recs) == 5
    for r in recs:
        assert "text" in r and r["text"]
        assert "rationale" in r
        assert 0.0 <= r["confidence"] <= 1.0


def test_prompt_contains_task_description_and_n(client, api_key, fake_llm):
    fake_llm.ollama.push_response(_valid_output(3))

    payload = {
        "task_description": "UNIQUE_RECS_TASK_MARKER",
        "max_recommendations": 3,
        "discipline": "Базы данных",
    }
    job_id = _post(client, api_key, payload)
    job = _get(client, api_key, job_id)

    assert job["status"] == "completed"
    p = job["llm_log"]["prompt"]
    assert "UNIQUE_RECS_TASK_MARKER" in p
    assert "Базы данных" in p
    # n=3 должно фигурировать в требовании к длине массива
    assert "3" in p


# ───────────── валидация JSON-схемы ─────────────

def test_retry_then_succeed(client, api_key, fake_llm):
    fake_llm.ollama.push_response("это не JSON")
    fake_llm.ollama.push_response(_valid_output(2))

    job_id = _post(client, api_key, {**VALID_PAYLOAD, "max_recommendations": 2})
    job = _get(client, api_key, job_id)

    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1
    assert len(job["result"]["recommendations"]) == 2
    assert "ПОВТОРНАЯ ПОПЫТКА" in fake_llm.ollama.calls[1]["prompt"]


def test_retry_exhausted_returns_failed(client, api_key, fake_llm):
    fake_llm.ollama.push_response("мусор 1")
    fake_llm.ollama.push_response("мусор 2")

    job_id = _post(client, api_key)
    job = _get(client, api_key, job_id)

    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_invalid_output"
    assert job["llm_log"]["retries"] == 1
    assert job["llm_log"]["raw_response"] == "мусор 2"


def test_invalid_confidence_triggers_retry(client, api_key, fake_llm):
    """confidence=1.5 нарушает ge=0..le=1 → ValidationError → retry."""
    bad = json.dumps({
        "recommendations": [
            {"text": "x", "rationale": "y", "confidence": 1.5},
        ]
    })
    fake_llm.ollama.push_response(bad)
    fake_llm.ollama.push_response(_valid_output(1))

    job_id = _post(client, api_key, {**VALID_PAYLOAD, "max_recommendations": 1})
    job = _get(client, api_key, job_id)
    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1


def test_empty_recommendations_list_triggers_retry(client, api_key, fake_llm):
    """Пустой массив нарушает min_length=1."""
    fake_llm.ollama.push_response(json.dumps({"recommendations": []}))
    fake_llm.ollama.push_response(_valid_output(1))

    job_id = _post(client, api_key, {**VALID_PAYLOAD, "max_recommendations": 1})
    job = _get(client, api_key, job_id)
    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1


# ───────────── сетевые ошибки ─────────────

def test_llm_unavailable(client, api_key, fake_llm):
    fake_llm.ollama.push_error(LLMUnavailable("ECONNREFUSED"))
    job_id = _post(client, api_key)
    job = _get(client, api_key, job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_unavailable"


def test_llm_timeout(client, api_key, fake_llm):
    fake_llm.ollama.push_error(LLMTimeout("timeout 120s"))
    job_id = _post(client, api_key)
    job = _get(client, api_key, job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_timeout"


# ───────────── валидация входа ─────────────

def test_max_recommendations_out_of_range(client, api_key):
    r = client.post(
        "/generate/recommendations",
        headers={"X-API-Key": api_key},
        json={"task_description": "x", "max_recommendations": 99},
    )
    assert r.status_code == 422


def test_missing_task_description(client, api_key):
    r = client.post(
        "/generate/recommendations",
        headers={"X-API-Key": api_key},
        json={"max_recommendations": 5},
    )
    assert r.status_code == 422
