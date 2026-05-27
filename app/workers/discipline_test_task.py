from __future__ import annotations

from app.config import settings
from app.schemas.llm_outputs import DisciplineLLMOutput
from app.services.prompt_builder import PromptBuilder
from app.workers._async_bridge import run_async
from app.workers._llm_runner import run_llm_task
from app.workers.celery_app import celery_app


def _stub_result() -> dict:
    return {
        "discipline": "Прочее",
        "confidence": 0.0,
        "note": "STUB: qwen3:8b недоступна, дисциплина не определена.",
    }


def _build_prompt(payload: dict) -> str:
    return PromptBuilder().build_discipline(
        text=payload.get("test_text", ""),
        kind="тест",
    )


@celery_app.task(name="app.workers.discipline_test_task.discipline_test_task")
def discipline_test_task(job_id: str) -> None:
    run_async(
        run_llm_task,
        job_id=job_id,
        target_model=settings.models.model_discipline,
        build_prompt=_build_prompt,
        output_schema=DisciplineLLMOutput,
        stub_result=_stub_result(),
        log_label="discipline_test_task",
    )
