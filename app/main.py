from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.routes_analyze import router as analyze_router
from app.api.routes_evaluate import router as evaluate_router
from app.api.routes_generate import router as generate_router
from app.api.routes_jobs import router as jobs_router
from app.config import settings
from app.middleware.auth import APIKeyMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.services.model_router import ModelRouter


def _configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        serialize=True,
        backtrace=False,
        diagnose=False,
        enqueue=False,
        level="INFO",
    )


_configure_logging()

app = FastAPI(title="LLM Grading Service", version="0.1.0")

# Middleware: auth должен сработать ВНУТРИ цикла логирования,
# то есть логирование добавляется ПОСЛЕДНИМ (выполняется первым на запросе).
app.add_middleware(APIKeyMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(generate_router)
app.include_router(evaluate_router)
app.include_router(analyze_router)
app.include_router(jobs_router)

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config", tags=["meta"])
async def get_public_config() -> dict:
    """Конфигурация без секретов — для отображения в sandbox.

    Показывает целевые модели по типам задач, текущий пул доступных,
    стратегию fallback и какую модель ModelRouter сейчас выбрал бы
    для каждой задачи. Не показывает API_KEY и Redis URL.
    """
    router = ModelRouter()

    tasks = {
        "evaluate": settings.models.model_evaluate,
        "recommendations": settings.models.model_recommendations,
        "testcases": settings.models.model_testcases,
        "discipline": settings.models.model_discipline,
        "embedding": settings.models.model_embedding,
    }

    resolutions = {}
    for name, target in tasks.items():
        actual, mode = router.resolve(target)
        resolutions[name] = {
            "target_model": target,
            "actual_model": actual,
            "model_resolution": mode,
        }

    return {
        "available_models": sorted(settings.models.available_set()),
        "fallback_strategy": settings.models.fallback_strategy,
        "fallback_model": settings.models.fallback_model,
        "tasks": resolutions,
    }


@app.get("/sandbox", tags=["ui"], include_in_schema=False)
async def sandbox() -> FileResponse:
    return FileResponse(str(_static_dir / "sandbox.html"), media_type="text/html")


@app.get("/ui-kit", tags=["ui"], include_in_schema=False)
async def ui_kit() -> FileResponse:
    return FileResponse(str(_static_dir / "ui-kit.html"), media_type="text/html")
