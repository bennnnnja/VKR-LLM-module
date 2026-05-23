from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendationsRequest(BaseModel):
    task_text: str = Field(..., description="Текст задания")
    student_answer: str = Field(..., description="Ответ студента")
    reference_answer: str | None = Field(None, description="Эталонный ответ (опционально)")
    focus: str | None = Field(None, description="На что особо обратить внимание")
