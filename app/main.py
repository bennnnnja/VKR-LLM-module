from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.routes_analyze import router as analyze_router
from app.api.routes_evaluate import router as evaluate_router
from app.api.routes_generate import router as generate_router
from app.api.routes_jobs import router as jobs_router
from app.middleware.auth import APIKeyMiddleware
from app.middleware.logging import RequestLoggingMiddleware


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

# Middleware: порядок имеет значение — auth должен сработать ВНУТРИ цикла логирования,
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
