from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.deps import get_job_store
from app.schemas.evaluate import EvaluateRequest
from app.schemas.job import Job, JobAcceptedResponse, JobType
from app.services.job_store import JobStoreAsync
from app.workers.evaluate_task import evaluate_task

router = APIRouter(prefix="/evaluate", tags=["evaluate"])


@router.post(
    "/task",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobAcceptedResponse,
)
async def post_evaluate_task(
    payload: EvaluateRequest,
    store: JobStoreAsync = Depends(get_job_store),
) -> JobAcceptedResponse:
    job = Job(job_type=JobType.evaluate, input_data=payload.model_dump())
    await store.create(job)
    evaluate_task.delay(job.job_id)
    return JobAcceptedResponse(jobId=job.job_id)
