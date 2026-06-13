from __future__ import annotations

import json

import pytest

from app.services.prompt_builder import PromptBuilder
from app.workers.celery_app import celery_app


@pytest.fixture(autouse=True)
def celery_eager():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture(autouse=True)
def all_models_available(monkeypatch):
    """testcases-таргет должен резолвиться в direct, чтобы дойти до промпта."""
    from app.config import ModelConfig
    monkeypatch.setenv(
        "AVAILABLE_MODELS",
        "qwen2.5:32b-instruct,qwen3-coder-next,qwen3:8b,qwen3-embedding:8b",
    )
    monkeypatch.setattr("app.services.model_router.settings.models", ModelConfig())


USER_NOTE = "UNIQUE_USER_PROMPT_MARKER: будь строже к терминологии"


def _job(client, api_key, url, payload):
    r = client.post(url, headers={"X-API-Key": api_key}, json=payload)
    assert r.status_code == 202, r.text
    job_id = r.json()["jobId"]
    r = client.get(f"/jobs/{job_id}", headers={"X-API-Key": api_key})
    return r.json()


# ───────────── user_prompt подмешивается в промпт ─────────────

def test_evaluate_user_prompt_in_prompt(client, api_key, fake_llm):
    job = _job(client, api_key, "/evaluate/task", {
        "task_text": "t", "reference_answer": "r", "student_answer": "s",
        "user_prompt": USER_NOTE,
    })
    assert job["status"] == "completed"
    p = job["llm_log"]["prompt"]
    assert USER_NOTE in p
    assert "ДОПОЛНИТЕЛЬНЫЕ УКАЗАНИЯ ОТ ПОЛЬЗОВАТЕЛЯ" in p


def test_evaluate_no_user_prompt_unchanged(client, api_key, fake_llm):
    job = _job(client, api_key, "/evaluate/task", {
        "task_text": "t", "reference_answer": "r", "student_answer": "s",
    })
    assert job["status"] == "completed"
    assert "ДОПОЛНИТЕЛЬНЫЕ УКАЗАНИЯ ОТ ПОЛЬЗОВАТЕЛЯ" not in job["llm_log"]["prompt"]


def test_recommendations_user_prompt_in_prompt(client, api_key, fake_llm):
    fake_llm.ollama.push_response(json.dumps({
        "recommendations": [{"text": "x", "rationale": "y", "confidence": 0.9}],
    }))
    job = _job(client, api_key, "/generate/recommendations", {
        "task_description": "Опиши SRP", "max_recommendations": 1,
        "user_prompt": USER_NOTE,
    })
    assert job["status"] == "completed"
    assert USER_NOTE in job["llm_log"]["prompt"]


def test_testcases_user_prompt_in_prompt(client, api_key, fake_llm):
    fake_llm.ollama.push_response(json.dumps({
        "cases": [{
            "ordinal_number": 1, "description": "d", "input": "1",
            "expected_output": "1", "type": "basic",
        }],
    }))
    job = _job(client, api_key, "/generate/testcases", {
        "task_description": "add(a,b)", "count": 1,
        "user_prompt": USER_NOTE,
    })
    assert job["status"] == "completed"
    assert USER_NOTE in job["llm_log"]["prompt"]


def test_empty_user_prompt_ignored(client, api_key, fake_llm):
    """Пустая строка / пробелы — блок не добавляется."""
    job = _job(client, api_key, "/evaluate/task", {
        "task_text": "t", "reference_answer": "r", "student_answer": "s",
        "user_prompt": "   ",
    })
    assert job["status"] == "completed"
    assert "ДОПОЛНИТЕЛЬНЫЕ УКАЗАНИЯ" not in job["llm_log"]["prompt"]


# ───────────── анти-markdown инструкция в промптах ─────────────

@pytest.mark.parametrize("build", [
    lambda b: b.build_evaluate("t", "r", "s"),
    lambda b: b.build_recommendations("t", 3),
    lambda b: b.build_testcases("t", 5, True, False),
])
def test_prompts_forbid_markdown_in_string_fields(build):
    p = build(PromptBuilder())
    assert "ТОЛЬКО ЧИСТЫЙ ТЕКСТ" in p
    assert "markdown" in p


def test_user_prompt_block_keeps_json_requirement():
    """Блок указаний напоминает, что JSON-формат остаётся обязательным."""
    p = PromptBuilder().build_evaluate("t", "r", "s", user_prompt="пиши кратко")
    idx_user = p.index("ДОПОЛНИТЕЛЬНЫЕ УКАЗАНИЯ ОТ ПОЛЬЗОВАТЕЛЯ")
    assert "JSON-формату выше остаются обязательными" in p[idx_user:]
