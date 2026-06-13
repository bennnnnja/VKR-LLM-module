from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    task_text: str = Field(..., min_length=1, description="Текст задания")
    reference_answer: str = Field(..., min_length=1, description="Эталонный ответ преподавателя")
    student_answer: str = Field(..., description="Ответ студента (может быть пустым)")
    rubric: Optional[str] = Field(
        None, description="Дополнительные критерии оценивания от преподавателя"
    )
    discipline: Optional[str] = Field(
        None, description="Дисциплина (используется в системной роли промпта)"
    )
    max_score: float = Field(
        100.0, ge=0.0, le=100.0,
        description="Шкала, в которой нужен итоговый балл. LLM всегда работает в 0..100; "
                    "при max_score!=100 в результат добавляется scaled_score.",
    )
    user_prompt: Optional[str] = Field(
        None,
        description="Опциональные указания пользователя — подмешиваются в промпт "
                    "перед вызовом LLM (корректируют содержание, не формат)",
    )
