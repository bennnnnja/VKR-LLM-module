from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "llm_grading",
    broker=settings.redis.redis_url,
    backend=settings.redis.redis_url,
    include=[
        "app.workers.evaluate_task",
        "app.workers.recommendations_task",
        "app.workers.testcases_task",
        "app.workers.discipline_test_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=settings.celery.celery_prefetch_multiplier,
    task_default_queue="llm_grading",
)
