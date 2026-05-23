from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.deps import get_job_store
from app.schemas.job import Job, JobCancelResponse, JobStatus
from app.services.job_store import JobStoreAsync
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    store: JobStoreAsync = Depends(get_job_store),
) -> Job:
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": job_id})
    return job


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(
    job_id: str,
    store: JobStoreAsync = Depends(get_job_store),
) -> JobCancelResponse:
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": job_id})

    if job.status in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "job_not_cancellable",
                "message": f"job is already in terminal status: {job.status.value}",
            },
        )

    if job.status == JobStatus.pending:
        # Сообщаем брокеру отозвать таск (если он ещё не подхвачен воркером).
        try:
            celery_app.control.revoke(job.job_id, terminate=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("celery revoke failed for {}: {}", job.job_id, exc)
        # И на всякий случай ставим cancel-флаг — если воркер всё-таки подхватит,
        # он остановится на первой проверке.
        await store.set_cancellation_requested(job_id)
        await store.set_finished(job_id, status=JobStatus.cancelled)
        return JobCancelResponse(jobId=job_id, status=JobStatus.cancelled)

    # in_progress
    await store.set_cancellation_requested(job_id)
    refreshed = await store.get(job_id)
    return JobCancelResponse(
        jobId=job_id,
        status=refreshed.status if refreshed else JobStatus.in_progress,
    )
