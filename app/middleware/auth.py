from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

# Пути, которым НЕ требуется X-API-Key
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/health",
    "/config",
    "/sandbox",
    "/ui-kit",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _PUBLIC_PREFIXES)


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _is_public(path):
            return await call_next(request)

        header = request.headers.get("x-api-key")
        if header is None or header != settings.auth.api_key:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "invalid or missing X-API-Key"}},
            )

        return await call_next(request)
