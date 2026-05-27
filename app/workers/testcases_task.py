from __future__ import annotations

from app.config import settings
from app.schemas.llm_outputs import TestcasesLLMOutput
from app.services.prompt_builder import PromptBuilder
from app.workers._async_bridge import run_async
from app.workers._llm_runner import run_llm_task
from app.workers.celery_app import celery_app


def _stub_result() -> dict:
    return {
        "cases": [],
        "note": "STUB: qwen3-coder-next недоступна, тест-кейсы не сгенерированы.",
    }


def _build_prompt(payload: dict) -> str:
    return PromptBuilder().build_testcases(
        task_description=payload.get("task_description", ""),
        count=int(payload.get("count") or 10),
        include_edge_cases=bool(payload.get("include_edge_cases", True)),
        include_negative_cases=bool(payload.get("include_negative_cases", False)),
        language=payload.get("language") or "python",
        function_signature=payload.get("function_signature"),
        generation_criteria=payload.get("generation_criteria"),
    )


@celery_app.task(name="app.workers.testcases_task.testcases_task")
def testcases_task(job_id: str) -> None:
    run_async(
        run_llm_task,
        job_id=job_id,
        target_model=settings.models.model_testcases,
        build_prompt=_build_prompt,
        output_schema=TestcasesLLMOutput,
        stub_result=_stub_result(),
        log_label="testcases_task",
    )
