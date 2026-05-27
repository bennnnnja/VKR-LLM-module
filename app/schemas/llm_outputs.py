from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.discipline import DisciplineName


class CriterionScore(BaseModel):
    name: str = Field(..., min_length=1)
    score: int = Field(..., ge=0, le=100)
    comment: str = Field("", description="Обоснование оценки по критерию")


class EvaluateLLMOutput(BaseModel):
    total_score: int = Field(..., ge=0, le=100)
    criteria: list[CriterionScore] = Field(..., min_length=1)
    summary: str = Field("", description="Общее заключение")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    similarity: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Косинусная близость reference/student (постобработка эмбеддером)",
    )

    @field_validator("strengths", "weaknesses", mode="before")
    @classmethod
    def _coerce_list(cls, v):
        if v is None:
            return []
        return v


class AlternativeAnswer(BaseModel):
    """Один правдоподобный корректный ответ студента, предлагаемый
    преподавателю как кандидат на принимаемую альтернативу эталона."""
    text: str = Field(..., min_length=1)
    rationale: str = Field("", description="Почему этот вариант корректен")
    confidence: float = Field(..., ge=0.0, le=1.0)


class RecommendationsLLMOutput(BaseModel):
    recommendations: list[AlternativeAnswer] = Field(..., min_length=1)


# ───────────────────────── testcases ─────────────────────────

TestCaseType = Literal["basic", "edge", "negative"]


class TestCase(BaseModel):
    """Один тест-кейс (чёрный ящик: пара вход/ожидаемый-результат)."""
    ordinal_number: int = Field(..., ge=1, description="Порядковый номер кейса 1..N")
    description: str = Field(..., min_length=1, description="Словесное описание сценария")
    input: str = Field("", description="Входные данные как строка")
    expected_output: str = Field(
        "",
        description=(
            "Ожидаемый вывод. Для type=negative — описание ожидаемого поведения "
            "(например 'raises ValueError' или 'возвращает None')"
        ),
    )
    type: TestCaseType


class TestcasesLLMOutput(BaseModel):
    cases: list[TestCase] = Field(..., min_length=1)


# ───────────────────────── discipline ─────────────────────────

class DisciplineLLMOutput(BaseModel):
    """Закрытый набор дисциплин — DisciplineName из app.schemas.discipline."""
    discipline: DisciplineName
    confidence: float = Field(..., ge=0.0, le=1.0)
