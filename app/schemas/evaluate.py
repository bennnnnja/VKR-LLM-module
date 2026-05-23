from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    task_text: str = Field(..., description="Текст задания")
    reference_answer: str = Field(..., description="Эталонный ответ преподавателя")
    student_answer: str = Field(..., description="Ответ студента")
    rubric: Optional[str] = Field(None, description="Опциональные критерии оценивания")
    max_score: float = Field(5.0, ge=0.0, le=100.0)
