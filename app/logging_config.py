from __future__ import annotations

import os
import sys

from loguru import logger

# LOG_FORMAT=text  → читаемый формат для разработки и демо (default)
# LOG_FORMAT=json  → одна JSON-строка на запись для прода/агрегации логов
# LOG_LEVEL=INFO|DEBUG|...

_DEFAULT_FORMAT = "<green>{time:HH:mm:ss}</green> | <level>{level: <5}</level> | <cyan>{message}</cyan>"


def setup() -> None:
    """Идемпотентная настройка loguru — можно звать и из API, и из воркера."""
    logger.remove()
    log_format = os.environ.get("LOG_FORMAT", "text").lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    if log_format == "json":
        logger.add(sys.stdout, serialize=True, level=log_level, enqueue=False)
    else:
        logger.add(
            sys.stdout,
            format=_DEFAULT_FORMAT,
            level=log_level,
            colorize=True,
            enqueue=False,
            backtrace=False,
            diagnose=False,
        )
