from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Закрытый набор дисциплин классификатора. Если LLM вернёт что-то не из
# этого списка — Pydantic-валидация отвергнет, сработает retry-механика
# в _llm_runner. При повторной неудаче — failed/llm_invalid_output.
DISCIPLINES: tuple[str, ...] = (
    "Программирование",
    "Математика",
    "Русский язык",
    "Литература",
    "Биология",
    "География",
    "Физика",
    "Прочее",
)

DisciplineName = Literal[
    "Программирование",
    "Математика",
    "Русский язык",
    "Литература",
    "Биология",
    "География",
    "Физика",
    "Прочее",
]


class DisciplineTestRequest(BaseModel):
    test_text: str = Field(..., min_length=1, description="Текст теста для классификации дисциплины")


class DisciplineTaskRequest(BaseModel):
    task_text: str = Field(..., min_length=1, description="Текст одного задания для классификации")


class DisciplineResponse(BaseModel):
    discipline: DisciplineName
    confidence: float = Field(..., ge=0.0, le=1.0)
