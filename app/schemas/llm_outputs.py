from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EvaluateLLMOutput(BaseModel):
    score: float = Field(..., ge=0.0)
    max_score: float = Field(..., gt=0.0)
    rationale: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    similarity: Optional[float] = Field(None, ge=0.0, le=1.0)


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
