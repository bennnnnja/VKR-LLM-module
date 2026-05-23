from __future__ import annotations

from typing import AsyncIterator

from app.services.job_store import JobStoreAsync


async def get_job_store() -> AsyncIterator[JobStoreAsync]:
    store = JobStoreAsync()
    try:
        yield store
    finally:
        await store.close()
