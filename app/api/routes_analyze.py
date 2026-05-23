from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, status

from app.deps import get_job_store
from app.schemas.discipline import (
    DisciplineResponse,
    DisciplineTaskRequest,
    DisciplineTestRequest,
)
from app.schemas.job import Job, JobAcceptedResponse, JobType
from app.services.job_store import JobStoreAsync
from app.workers.discipline_test_task import discipline_test_task

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post(
    "/test-discipline",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
)
async def post_test_discipline(
    payload: DisciplineTestRequest,
    store: JobStoreAsync = Depends(get_job_store),
) -> JobAcceptedResponse:
    job = Job(job_type=JobType.discipline_test, input_data=payload.model_dump())
    await store.create(job)
    discipline_test_task.delay(job.job_id)
    return JobAcceptedResponse(jobId=job.job_id)


@router.post(
    "/task-discipline",
    status_code=status.HTTP_200_OK,
    response_model=DisciplineResponse,
)
async def post_task_discipline(payload: DisciplineTaskRequest) -> DisciplineResponse:
    # Единственный синхронный эндпоинт — без Celery, без JobStore.
    # На фазе 1 — фиксированный mock. Реальный qwen3:8b — в фазе 3.
    await asyncio.sleep(1)
    return DisciplineResponse(discipline="Программирование", confidence=0.75)
