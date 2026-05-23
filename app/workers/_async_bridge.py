from __future__ import annotations

import asyncio
import threading
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


def run_async(coro_factory: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    """Запускает async-функцию из синхронного кода.

    В реальном Celery-воркере (отдельный процесс/поток, без event loop)
    используется обычный asyncio.run. В тестах с task_always_eager
    Celery-таск вызывается из уже работающего FastAPI-loop'а — там
    asyncio.run падает с "cannot be called from a running event loop";
    в этом случае поднимаем коротко живущий поток и крутим loop там.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory(*args, **kwargs))

    err: list[BaseException] = []
    res: list[T] = []

    def _runner() -> None:
        try:
            res.append(asyncio.run(coro_factory(*args, **kwargs)))
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    thread = threading.Thread(target=_runner, name="async-bridge", daemon=True)
    thread.start()
    thread.join()
    if err:
        raise err[0]
    return res[0]
