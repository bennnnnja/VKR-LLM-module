from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.deps import get_job_store
from app.schemas.job import Job, JobAcceptedResponse, JobType
from app.schemas.recommendations import RecommendationsRequest
from app.schemas.testcases import TestcasesRequest
from app.services.job_store import JobStoreAsync
from app.workers.recommendations_task import recommendations_task
from app.workers.testcases_task import testcases_task

router = APIRouter(prefix="/generate", tags=["generate"])


@router.post(
    "/testcases",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
)
async def post_testcases(
    payload: TestcasesRequest,
    store: JobStoreAsync = Depends(get_job_store),
) -> JobAcceptedResponse:
    job = Job(job_type=JobType.testcases, input_data=payload.model_dump())
    await store.create(job)
    testcases_task.delay(job.job_id)
    return JobAcceptedResponse(jobId=job.job_id)


@router.post(
    "/recommendations",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
)
async def post_recommendations(
    payload: RecommendationsRequest,
    store: JobStoreAsync = Depends(get_job_store),
) -> JobAcceptedResponse:
    job = Job(job_type=JobType.recommendations, input_data=payload.model_dump())
    await store.create(job)
    recommendations_task.delay(job.job_id)
    return JobAcceptedResponse(jobId=job.job_id)
