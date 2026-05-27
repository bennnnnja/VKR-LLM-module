from __future__ import annotations

import json

import pytest

from app.services.llm_client import LLMTimeout, LLMUnavailable


@pytest.fixture(autouse=True)
def add_discipline_model_to_available(monkeypatch):
    """Включаем qwen3:8b в available_models, чтобы sync-эндпоинт
    уходил в direct, а не в stub."""
    monkeypatch.setenv("AVAILABLE_MODELS", "qwen2.5:32b-instruct,qwen3-coder-next,qwen3:8b,qwen3-embedding:8b")
    from app.config import ModelConfig
    monkeypatch.setattr(
        "app.services.model_router.settings.models",
        ModelConfig(),
    )
    # роутер в sync-эндпоинте читает settings напрямую — патчим и там
    monkeypatch.setattr(
        "app.api.routes_analyze.settings.models",
        ModelConfig(),
    )


# ───────────── sync (/analyze/task-discipline) ─────────────

def _post_sync(client, api_key, text="Пересказать смысл книги Мастер и Маргарита."):
    return client.post(
        "/analyze/task-discipline",
        headers={"X-API-Key": api_key},
        json={"task_text": text},
    )


def test_sync_direct_success(client, api_key, fake_llm):
    fake_llm.ollama.push_response(json.dumps({
        "discipline": "Литература", "confidence": 0.92,
    }))
    r = _post_sync(client, api_key)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["discipline"] == "Литература"
    assert body["confidence"] == pytest.approx(0.92)


def test_sync_invalid_then_retry_succeed(client, api_key, fake_llm):
    fake_llm.ollama.push_response(json.dumps({"discipline": "Информатика", "confidence": 0.9}))
    fake_llm.ollama.push_response(json.dumps({"discipline": "Программирование", "confidence": 0.8}))
    r = _post_sync(client, api_key, "Напиши быструю сортировку")
    assert r.status_code == 200
    assert r.json()["discipline"] == "Программирование"


def test_sync_invalid_twice_returns_502(client, api_key, fake_llm):
    fake_llm.ollama.push_response(json.dumps({"discipline": "Алгебра", "confidence": 0.9}))
    fake_llm.ollama.push_response(json.dumps({"discipline": "Геометрия", "confidence": 0.9}))
    r = _post_sync(client, api_key)
    assert r.status_code == 502
    body = r.json()
    assert body["detail"]["code"] == "llm_invalid_output"


def test_sync_unavailable_returns_502(client, api_key, fake_llm):
    fake_llm.ollama.push_error(LLMUnavailable("ECONNREFUSED"))
    r = _post_sync(client, api_key)
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "llm_unavailable"


def test_sync_timeout_returns_504(client, api_key, fake_llm):
    fake_llm.ollama.push_error(LLMTimeout("timeout 30s"))
    r = _post_sync(client, api_key)
    assert r.status_code == 504
    assert r.json()["detail"]["code"] == "llm_timeout"


def test_sync_master_margarita_classified_as_literature(client, api_key, fake_llm):
    """'Мастер и Маргарита' → Литература. Прямой repro пользовательского бага."""
    fake_llm.ollama.push_response(json.dumps({
        "discipline": "Литература", "confidence": 0.95,
    }))
    r = _post_sync(client, api_key)
    assert r.status_code == 200
    body = r.json()
    assert body["discipline"] == "Литература"
    # И в промпте действительно был задан текст
    assert any("Мастер и Маргарита" in call["prompt"] for call in fake_llm.ollama.calls)


def test_sync_passes_timeout_override(client, api_key, fake_llm):
    """Sync-эндпоинт должен вызывать generate(..., timeout=30) — отдельный
    таймаут SYNC_LLM_TIMEOUT_SECONDS, не общий 120с."""
    orig_generate = fake_llm.ollama.generate
    captured = {}

    async def wrapped(prompt, model, format="json", timeout=None, **kw):
        captured["timeout"] = timeout
        return await orig_generate(prompt, model, format)

    fake_llm.ollama.generate = wrapped  # type: ignore
    fake_llm.ollama.push_response(json.dumps({"discipline": "Прочее", "confidence": 0.5}))

    r = _post_sync(client, api_key)
    assert r.status_code == 200
    assert captured["timeout"] == 30  # default SYNC_LLM_TIMEOUT_SECONDS


def test_sync_validation_empty_body(client, api_key):
    r = client.post(
        "/analyze/task-discipline",
        headers={"X-API-Key": api_key},
        json={},
    )
    assert r.status_code == 422


def test_sync_all_disciplines_accepted(client, api_key, fake_llm):
    """Все 8 значений closed-set проходят валидацию через sync."""
    from app.schemas.discipline import DISCIPLINES
    for d in DISCIPLINES:
        fake_llm.ollama.push_response(json.dumps({"discipline": d, "confidence": 0.7}))
        r = _post_sync(client, api_key, f"Текст про {d}")
        assert r.status_code == 200, f"{d} should be accepted"
        assert r.json()["discipline"] == d


def test_sync_stub_when_model_unavailable(client, api_key, monkeypatch):
    """Если qwen3:8b не в AVAILABLE_MODELS — sync отдаёт 'Прочее'/0.0
    без вызова LLM (а не выдумывает Программирование/0.75 как в phase 1)."""
    monkeypatch.setenv("AVAILABLE_MODELS", "qwen2.5:32b-instruct")
    from app.config import ModelConfig
    monkeypatch.setattr("app.services.model_router.settings.models", ModelConfig())
    monkeypatch.setattr("app.api.routes_analyze.settings.models", ModelConfig())

    r = _post_sync(client, api_key, "Что угодно")
    assert r.status_code == 200
    body = r.json()
    assert body["discipline"] == "Прочее"
    assert body["confidence"] == 0.0


# ───────────── /config резолюция discipline после расширения available_models ─────────────

def test_config_shows_direct_when_qwen3_8b_available(client):
    """После добавления qwen3:8b в AVAILABLE_MODELS — preview становится direct."""
    body = client.get("/config").json()
    assert body["tasks"]["discipline"]["target_model"] == "qwen3:8b"
    assert body["tasks"]["discipline"]["model_resolution"] == "direct"
