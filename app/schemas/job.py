from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobType(str, Enum):
    evaluate = "evaluate"
    recommendations = "recommendations"
    testcases = "testcases"
    discipline_test = "discipline_test"
    discipline_task = "discipline_task"


ModelResolution = Literal["direct", "fallback", "stub", "fail"]


class JobError(BaseModel):
    code: str
    message: str


class LLMLog(BaseModel):
    target_model: str
    actual_model: str
    model_resolution: ModelResolution
    prompt: str = ""
    raw_response: str = ""
    duration_ms: int = 0
    retries: int = 0


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    job_type: JobType
    status: JobStatus = JobStatus.pending
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    input_data: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    error: Optional[JobError] = None
    llm_log: Optional[LLMLog] = None

    def touch(self) -> None:
        self.updated_at = _utcnow_iso()


class JobAcceptedResponse(BaseModel):
    jobId: str


class JobCancelResponse(BaseModel):
    jobId: str
    status: JobStatus
