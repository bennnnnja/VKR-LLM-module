from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OllamaConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    ollama_base_url: str = "http://ollama.example.dvfu.local:11434"
    llm_timeout_seconds: int = 120
    # Жёсткий таймаут для синхронного эндпоинта /analyze/task-discipline:
    # клиент держит HTTP-соединение открытым всё время вызова LLM,
    # поэтому ограничение строже общего.
    sync_llm_timeout_seconds: int = 30
    llm_max_concurrent: int = 2


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    redis_url: str = "redis://redis:6379/0"
    job_ttl_seconds: int = 86400


class ModelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    model_evaluate: str = "qwen2.5:32b-instruct"
    model_recommendations: str = "qwen2.5:32b-instruct"
    model_testcases: str = "qwen3-coder-next"
    model_discipline: str = "qwen3:8b"
    model_embedding: str = "qwen3-embedding:8b"

    available_models: str = "qwen2.5:32b-instruct"

    fallback_strategy: Literal["stub", "fallback", "fail"] = "stub"
    fallback_model: str = "qwen2.5:32b-instruct"

    def available_set(self) -> set[str]:
        return {m.strip() for m in self.available_models.split(",") if m.strip()}


class CeleryConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    celery_worker_concurrency: int = 2
    celery_prefetch_multiplier: int = 1


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    api_key: str = "replace-me-with-strong-random-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
