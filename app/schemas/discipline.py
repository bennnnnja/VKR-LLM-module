from __future__ import annotations

from pydantic import BaseModel, Field


class DisciplineTestRequest(BaseModel):
    test_text: str = Field(..., description="Текст теста для классификации дисциплины")


class DisciplineTaskRequest(BaseModel):
    task_text: str = Field(..., description="Текст одного задания для классификации")


class DisciplineResponse(BaseModel):
    discipline: str
    confidence: float = Field(..., ge=0.0, le=1.0)
