from __future__ import annotations

import json

import pytest

from app.services.llm_client import LLMTimeout, LLMUnavailable
from app.workers.celery_app import celery_app


@pytest.fixture(autouse=True)
def celery_eager():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture(autouse=True)
def add_testcases_model_to_available(monkeypatch):
    """В тестовом окружении явно включаем target-модель тест-кейсов
    в available_models, чтобы model_resolution стал direct."""
    monkeypatch.setenv("AVAILABLE_MODELS", "qwen2.5:32b-instruct,qwen3-coder-next,qwen3:8b,qwen3-embedding:8b")
    # Сбросить кэш settings
    from app.config import get_settings, ModelConfig
    monkeypatch.setattr(
        "app.services.model_router.settings.models",
        ModelConfig(),
    )


VALID_PAYLOAD = {
    "task_description": "Написать функцию add(a: int, b: int) -> int, возвращающую сумму двух целых чисел.",
    "function_signature": "def add(a: int, b: int) -> int",
    "language": "python",
    "count": 5,
    "include_edge_cases": True,
    "include_negative_cases": False,
}


def _valid_output(n: int = 5, types: list[str] | None = None) -> str:
    types = types or (["basic"] * n)
    return json.dumps({
        "cases": [
            {
                "ordinal_number": i + 1,
                "description": f"Сценарий #{i + 1}",
                "input": f"{i} {i + 1}",
                "expected_output": f"{2 * i + 1}",
                "type": types[i],
            }
            for i in range(n)
        ]
    })


def _post(client, api_key, payload=None):
    payload = payload or VALID_PAYLOAD
    r = client.post(
        "/generate/testcases",
        headers={"X-API-Key": api_key},
        json=payload,
    )
    assert r.status_code == 202, r.text
    return r.json()["jobId"]


def _get(client, api_key, job_id):
    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    assert r.status_code == 200
    return r.json()


# ───────────── happy path ─────────────

def test_direct_mode_success(client, api_key, fake_llm):
    fake_llm.ollama.push_response(_valid_output(5))

    job_id = _post(client, api_key)
    job = _get(client, api_key, job_id)

    assert job["status"] == "completed"
    assert job["llm_log"]["target_model"] == "qwen3-coder-next"
    assert job["llm_log"]["actual_model"] == "qwen3-coder-next"
    assert job["llm_log"]["model_resolution"] == "direct"
    assert job["llm_log"]["retries"] == 0

    cases = job["result"]["cases"]
    assert len(cases) == 5
    for i, c in enumerate(cases):
        assert c["ordinal_number"] == i + 1
        assert c["description"]
        assert c["type"] in ("basic", "edge", "negative")


def test_prompt_contains_task_signature_and_flags(client, api_key, fake_llm):
    fake_llm.ollama.push_response(_valid_output(3))
    payload = {
        "task_description": "UNIQUE_TC_MARKER",
        "function_signature": "def my_func(x: list[int]) -> int",
        "count": 3,
        "include_edge_cases": True,
        "include_negative_cases": True,
        "language": "python",
        "generation_criteria": {"max_array_size": 1000, "allow_unicode": False},
    }
    job_id = _post(client, api_key, payload)
    job = _get(client, api_key, job_id)
    assert job["status"] == "completed"
    p = job["llm_log"]["prompt"]
    assert "UNIQUE_TC_MARKER" in p
    assert "def my_func(x: list[int]) -> int" in p
    assert "include_edge_cases): true" in p or "(type=\"edge\"): true" in p
    assert "include_negative_cases): true" in p or "(type=\"negative\"): true" in p
    assert "max_array_size" in p
    assert "ровно 3 элементов" in p


# ───────────── retry ─────────────

def test_retry_then_succeed(client, api_key, fake_llm):
    fake_llm.ollama.push_response("это не JSON")
    fake_llm.ollama.push_response(_valid_output(2))

    job_id = _post(client, api_key, {**VALID_PAYLOAD, "count": 2})
    job = _get(client, api_key, job_id)
    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1
    assert len(job["result"]["cases"]) == 2


def test_retry_exhausted_returns_failed(client, api_key, fake_llm):
    fake_llm.ollama.push_response("мусор 1")
    fake_llm.ollama.push_response("мусор 2")

    job_id = _post(client, api_key)
    job = _get(client, api_key, job_id)
    assert job["status"] == "failed"
    assert job["error"]["code"] == "llm_invalid_output"
    assert job["llm_log"]["retries"] == 1


def test_invalid_type_value_triggers_retry(client, api_key, fake_llm):
    """type='stress' не из enum → ValidationError → retry."""
    bad = json.dumps({
        "cases": [
            {"ordinal_number": 1, "description": "x", "input": "1", "expected_output": "1", "type": "stress"},
        ]
    })
    fake_llm.ollama.push_response(bad)
    fake_llm.ollama.push_response(_valid_output(1))

    job_id = _post(client, api_key, {**VALID_PAYLOAD, "count": 1})
    job = _get(client, api_key, job_id)
    assert job["status"] == "completed"
    assert job["llm_log"]["retries"] == 1


def test_empty_cases_triggers_retry(client, api_key, fake_llm):
    """min_length=1 → пустой массив → retry."""
    fake_llm.ollama.push_response(json.dumps({"cases": []}))
    fake_llm.ollama.push_response(_valid_output(1))

    job_id = _post(client, api_key, {**VALID_PAYLOAD, "count": 1})
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

def test_count_too_high(client, api_key):
    r = client.post(
        "/generate/testcases",
        headers={"X-API-Key": api_key},
        json={"task_description": "x", "count": 51},
    )
    assert r.status_code == 422


def test_count_too_low(client, api_key):
    r = client.post(
        "/generate/testcases",
        headers={"X-API-Key": api_key},
        json={"task_description": "x", "count": 0},
    )
    assert r.status_code == 422


def test_missing_task_description(client, api_key):
    r = client.post(
        "/generate/testcases",
        headers={"X-API-Key": api_key},
        json={"count": 5},
    )
    assert r.status_code == 422


def test_old_shape_task_text_rejected(client, api_key):
    """Старая форма (task_text вместо task_description) больше не валидна."""
    r = client.post(
        "/generate/testcases",
        headers={"X-API-Key": api_key},
        json={"task_text": "x", "count": 5},
    )
    assert r.status_code == 422


def test_mixed_case_types_preserved(client, api_key, fake_llm):
    """type заполняется LLM, мы его не трогаем — должны увидеть в result."""
    out = _valid_output(3, types=["basic", "edge", "negative"])
    fake_llm.ollama.push_response(out)
    job_id = _post(client, api_key, {**VALID_PAYLOAD, "count": 3, "include_negative_cases": True})
    job = _get(client, api_key, job_id)
    assert job["status"] == "completed"
    types = [c["type"] for c in job["result"]["cases"]]
    assert types == ["basic", "edge", "negative"]
