from __future__ import annotations

from typing import Literal

from app.config import ModelConfig, settings

ResolutionMode = Literal["direct", "fallback", "stub", "fail"]


class ModelRouter:
    """Принимает решение, какую модель физически вызывать для целевой задачи.

    Поведение полностью определяется текущей ModelConfig (available_models,
    fallback_strategy, fallback_model). Результат — (actual_model, mode),
    где actual_model — то, что воркер реально передаст в Ollama (или то,
    что будет помечено в логе при stub/fail), а mode — направление,
    которое воркер запишет в llm_log.model_resolution.
    """

    def __init__(self, config: ModelConfig | None = None) -> None:
        self._config = config or settings.models

    def resolve(self, target_model: str) -> tuple[str, ResolutionMode]:
        available = self._config.available_set()

        if target_model in available:
            return (target_model, "direct")

        strategy = self._config.fallback_strategy

        if strategy == "fallback":
            fallback = self._config.fallback_model
            if fallback in available:
                return (fallback, "fallback")
            return (target_model, "fail")

        if strategy == "stub":
            return (target_model, "stub")

        return (target_model, "fail")
