from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RecommendationsRequest(BaseModel):
    task_description: str = Field(
        ..., min_length=1,
        description="Формулировка учебного задания открытого типа",
    )
    max_recommendations: int = Field(
        5, ge=1, le=10,
        description="Сколько альтернативных правильных ответов сгенерировать",
    )
    discipline: Optional[str] = Field(
        None, description="Дисциплина (используется в системной роли промпта)",
    )
    user_prompt: Optional[str] = Field(
        None,
        description="Опциональные указания пользователя — подмешиваются в промпт "
                    "перед вызовом LLM (корректируют содержание, не формат)",
    )
