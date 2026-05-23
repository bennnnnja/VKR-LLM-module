from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


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


class RecommendationItem(BaseModel):
    title: str
    detail: str
    priority: int = Field(1, ge=1, le=5)


class RecommendationsLLMOutput(BaseModel):
    items: list[RecommendationItem]
    summary: str = ""


class TestCase(BaseModel):
    name: str
    input: str
    expected_output: str
    is_edge_case: bool = False


class TestcasesLLMOutput(BaseModel):
    cases: list[TestCase]


class DisciplineLLMOutput(BaseModel):
    discipline: str
    confidence: float = Field(..., ge=0.0, le=1.0)
