from __future__ import annotations

from app.config import ModelConfig
from app.services.model_router import ModelRouter


def _router(**overrides) -> ModelRouter:
    cfg = ModelConfig(**overrides)
    return ModelRouter(config=cfg)


def test_resolve_direct_when_target_available():
    router = _router(available_models="qwen2.5:32b-instruct")
    assert router.resolve("qwen2.5:32b-instruct") == ("qwen2.5:32b-instruct", "direct")


def test_resolve_fallback_when_strategy_fallback_and_fallback_available():
    router = _router(
        available_models="qwen2.5:32b-instruct",
        fallback_strategy="fallback",
        fallback_model="qwen2.5:32b-instruct",
    )
    assert router.resolve("qwen3-coder-next") == ("qwen2.5:32b-instruct", "fallback")


def test_resolve_stub_when_strategy_stub():
    router = _router(
        available_models="qwen2.5:32b-instruct",
        fallback_strategy="stub",
    )
    assert router.resolve("qwen3:8b") == ("qwen3:8b", "stub")


def test_resolve_fail_when_strategy_fail():
    router = _router(
        available_models="qwen2.5:32b-instruct",
        fallback_strategy="fail",
    )
    assert router.resolve("qwen3:8b") == ("qwen3:8b", "fail")


def test_resolve_fail_when_strategy_fallback_but_fallback_also_unavailable():
    router = _router(
        available_models="qwen2.5:32b-instruct",
        fallback_strategy="fallback",
        fallback_model="some-other-model",
    )
    assert router.resolve("qwen3:8b") == ("qwen3:8b", "fail")
