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
    "task_text": "Объясните принцип работы виртуальной памяти.",
    "reference_answer": "Виртуальная память — абстракция, дающая процессу плоское адресное пространство; страницы транслируются в физические через таблицы страниц...",
    "student_answer": "Это когда программа думает что у неё много памяти, а на самом деле ОС её эмулирует.",
}


def _post_evaluate(client, api_key, payload=None):
    payload = payload or VALID_PAYLOAD
    r = client.post("/evaluate/task", headers={"X-API-Key": api_key}, json=payload)
    assert r.status_code == 202, r.text
    return r.json()["jobId"]


def _get_job(client, api_key, job_id):
    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    return r.json()


# ───────────────── direct mode: успешный кейс ─────────────────

def test_direct_mode_success_with_default_fake(client, api_key, fake_llm):
    """Default FakeOllamaClient возвращает валидный JSON по схеме."""
    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)

    assert job["status"] == "completed"
    assert job["llm_log"]["model_resolution"] == "direct"
    assert job["llm_log"]["target_model"] == "qwen2.5:32b-instruct"
    assert job["llm_log"]["actual_model"] == "qwen2.5:32b-instruct"
    assert job["llm_log"]["retries"] == 0
    assert job["llm_log"]["prompt"]  # реальный промпт записан
    assert job["llm_log"]["raw_response"]
    assert job["llm_log"]["duration_ms"] > 0

    res = job["result"]
    assert 0 <= res["total_score"] <= 100
    assert len(res["criteria"]) >= 1
    assert "summary" in res
    assert "strengths" in res
    assert "similarity" not in res  # по умолчанию embedder отключён

    # Клиент действительно был вызван
    assert len(fake_llm.ollama.calls) == 1
    assert fake_llm.ollama.calls[0]["model"] == "qwen2.5:32b-instruct"


def test_prompt_contains_inputs(client, api_key, fake_llm):
    payload = {
        "task_text": "UNIQUE_TASK_MARKER",
        "reference_answer": "UNIQUE_REF_MARKER",
        "student_answer": "UNIQUE_STUDENT_MARKER",
        "discipline": "Программирование",
        "rubric": "Особое внимание на корректность примеров кода",
    }
    job_id = _post_evaluate(client, api_key, payload)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "completed"
    p = job["llm_log"]["prompt"]
    assert "UNIQUE_TASK_MARKER" in p
    assert "UNIQUE_REF_MARKER" in p
    assert "UNIQUE_STUDENT_MARKER" in p
    assert "Программирование" in p
    assert "корректность примеров кода" in p


# ───────────────── retry на невалидный output ─────────────────

def test_invalid_output_then_retry_then_succeed(client, api_key, fake_llm):
    """Первый ответ — мусор, retry — валидный JSON. status=completed, retries=1."""
    fake_llm.ollama.push_response("это не JSON вообще")
    fake_llm.ollama.push_response(json.dumps({
        "total_score": 50,
        "criteria": [{"name": "Точность", "score": 50, "comment": "ok"}],
        "summary": "retried",
        "strengths": [], "weaknesses": [],
    }))

    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)

    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1
    assert job["result"]["summary"] == "retried"
    assert len(fake_llm.ollama.calls) == 2
    # Второй промпт содержит блок «ПОВТОРНАЯ ПОПЫТКА»
    assert "ПОВТОРНАЯ ПОПЫТКА" in fake_llm.ollama.calls[1]["prompt"]


def test_invalid_output_twice_returns_failed(client, api_key, fake_llm):
    """Оба ответа невалидны → failed с llm_invalid_output."""
    fake_llm.ollama.push_response("первый мусор")
    fake_llm.ollama.push_response("второй мусор")

    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)

    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_invalid_output"
    assert job["llm_log"]["retries"] == 1
    assert job["llm_log"]["raw_response"] == "второй мусор"
    assert job["result"] is None


def test_invalid_schema_value_triggers_retry(client, api_key, fake_llm):
    """JSON синтаксически валидный, но total_score=150 (вне 0..100)."""
    bad = json.dumps({
        "total_score": 150,
        "criteria": [{"name": "Точность", "score": 50, "comment": "x"}],
        "summary": "x", "strengths": [], "weaknesses": [],
    })
    good = json.dumps({
        "total_score": 60,
        "criteria": [{"name": "Точность", "score": 60, "comment": "x"}],
        "summary": "fixed", "strengths": [], "weaknesses": [],
    })
    fake_llm.ollama.push_response(bad)
    fake_llm.ollama.push_response(good)

    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1
    assert job["result"]["total_score"] == 60


# ───────────────── LLMUnavailable / LLMTimeout ─────────────────

def test_llm_unavailable_returns_failed(client, api_key, fake_llm):
    fake_llm.ollama.push_error(LLMUnavailable("ECONNREFUSED ollama.example.dvfu.local:11434"))
    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_unavailable"
    assert "ECONNREFUSED" in job["error"]["message"]
    assert job["llm_log"]["model_resolution"] == "direct"


def test_llm_timeout_returns_failed(client, api_key, fake_llm):
    fake_llm.ollama.push_error(LLMTimeout("timeout after 120s"))
    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_timeout"


# ───────────────── similarity post-processing ─────────────────

def test_similarity_added_when_embedder_returns_vectors(client, api_key, fake_llm):
    fake_llm.embed.push([1.0, 0.0, 0.0])  # reference
    fake_llm.embed.push([1.0, 0.0, 0.0])  # student — идентично
    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "completed"
    assert "similarity" in job["result"]
    assert job["result"]["similarity"] == pytest.approx(1.0, abs=1e-4)


def test_similarity_skipped_when_embedder_returns_none(client, api_key, fake_llm):
    # Никаких push() на embed — default None → similarity отсутствует
    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "completed"
    assert "similarity" not in job["result"]


def test_similarity_low_for_orthogonal_vectors(client, api_key, fake_llm):
    fake_llm.embed.push([1.0, 0.0, 0.0])
    fake_llm.embed.push([0.0, 1.0, 0.0])
    job_id = _post_evaluate(client, api_key)
    job = _get_job(client, api_key, job_id)
    assert job["status"] == "completed"
    assert job["result"]["similarity"] == pytest.approx(0.0, abs=1e-4)


# ───────────────── scaled_score ─────────────────

def test_scaled_score_when_max_score_not_100(client, api_key, fake_llm):
    fake_llm.ollama.push_response(json.dumps({
        "total_score": 80,
        "criteria": [{"name": "X", "score": 80, "comment": "y"}],
        "summary": "s", "strengths": [], "weaknesses": [],
    }))
    payload = {**VALID_PAYLOAD, "max_score": 5.0}
    job_id = _post_evaluate(client, api_key, payload)
    job = _get_job(client, api_key, job_id)
    assert job["result"]["total_score"] == 80
    assert job["result"]["scaled_score"] == pytest.approx(4.0)
    assert job["result"]["scaled_max"] == 5.0
