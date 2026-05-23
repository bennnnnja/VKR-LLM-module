from __future__ import annotations

from pydantic import BaseModel, Field


class TestcasesRequest(BaseModel):
    task_text: str = Field(..., description="Описание задания на программирование")
    language: str = Field("python", description="Язык программирования")
    count: int = Field(5, ge=1, le=50, description="Сколько тест-кейсов сгенерировать")
    include_edge_cases: bool = True
