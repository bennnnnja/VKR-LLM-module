from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_template(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def render(name: str, **kwargs: object) -> str:
    """Очень простой шаблонизатор: str.format на содержимом файла промпта.

    В фазах 3-4 здесь появится валидация наличия плейсхолдеров и т.п.
    """
    template = load_template(name)
    return template.format(**kwargs)
