from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.job import Job, JobError, JobStatus, JobType, LLMLog


def test_job_defaults():
    job = Job(job_type=JobType.evaluate)
    assert job.status == JobStatus.pending
    assert job.job_id  # uuid сгенерирован
    assert job.created_at
    assert job.updated_at  # touch() ещё не вызывался — но обе метки выставлены
    assert job.result is None
    assert job.error is None
    assert job.llm_log is None


def test_job_roundtrip_json():
    job = Job(
        job_type=JobType.testcases,
        input_data={"task_text": "x"},
    )
    job.llm_log = LLMLog(
        target_model="qwen3-coder-next",
        actual_model="qwen2.5:32b-instruct",
        model_resolution="fallback",
        duration_ms=1234,
    )
    job.error = JobError(code="x", message="y")
    raw = job.model_dump_json()
    restored = Job.model_validate_json(raw)
    assert restored.llm_log.model_resolution == "fallback"
    assert restored.error.code == "x"


def test_llm_log_resolution_must_be_valid():
    with pytest.raises(ValidationError):
        LLMLog(
            target_model="x",
            actual_model="y",
            model_resolution="totally-wrong",  # type: ignore[arg-type]
        )
