from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Пути, для которых нужно явно отключить браузерный кеш. Иначе после
# обновления статики (sandbox.html / ui-kit.html / components/*.js)
# браузер показывает старую версию из disk cache, а бэк ждёт новую
# схему запроса — известный кейс с testcases-формой в фазе 6→7.
_NO_STORE_PREFIXES: tuple[str, ...] = (
    "/sandbox",
    "/ui-kit",
    "/static",
    "/",  # сам редирект на sandbox
)


def _needs_no_store(path: str) -> bool:
    if path == "/":
        return True
    return any(path == p or path.startswith(p + "/") for p in _NO_STORE_PREFIXES if p != "/")


class NoStoreCacheMiddleware(BaseHTTPMiddleware):
    """Ставит Cache-Control: no-store на UI-роуты и статику.

    Не трогает API-роуты — для них кеш и так нерелевантен (POST/JSON),
    но и явно блокировать незачем.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if _needs_no_store(request.url.path):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
