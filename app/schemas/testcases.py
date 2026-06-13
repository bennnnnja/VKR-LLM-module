from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TestcasesRequest(BaseModel):
    """Запрос на генерацию тест-кейсов под задачу программирования (ВКР, п.4.2)."""

    task_description: str = Field(
        ..., min_length=1,
        description="Описание задания на написание кода",
    )
    function_signature: Optional[str] = Field(
        None,
        description="Опциональная сигнатура функции, например 'def add(a: int, b: int) -> int'",
    )
    count: int = Field(
        10, ge=1, le=50,
        description="Сколько тест-кейсов сгенерировать (default 10, max 50)",
    )
    include_edge_cases: bool = Field(
        True, description="Включать ли граничные кейсы (type='edge')",
    )
    include_negative_cases: bool = Field(
        False, description="Включать ли кейсы с невалидным вводом (type='negative')",
    )
    language: Optional[str] = Field(
        "python",
        description="Язык — используется как подсказка LLM для подбора реалистичных типов",
    )
    generation_criteria: Optional[dict[str, Any]] = Field(
        None,
        description="Свободный bag параметров генерации (передаётся в промпт как контекст)",
    )
    user_prompt: Optional[str] = Field(
        None,
        description="Опциональные указания пользователя — подмешиваются в промпт "
                    "перед вызовом LLM (корректируют содержание, не формат)",
    )
