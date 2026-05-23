from __future__ import annotations

from pathlib import Path
from typing import Optional

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


class PromptBuilder:
    """Сборка промптов для разных задач. Тексты — в app/prompts/*.txt."""

    def build_evaluate(
        self,
        task_description: str,
        reference_answer: str,
        student_answer: str,
        discipline: Optional[str] = None,
        rubric: Optional[str] = None,
    ) -> str:
        template = _load("evaluate.txt")

        discipline_suffix = (
            f' по дисциплине "{discipline.strip()}"'
            if discipline and discipline.strip()
            else ""
        )
        rubric_block = (
            f"\nДОПОЛНИТЕЛЬНЫЕ КРИТЕРИИ ОТ ПРЕПОДАВАТЕЛЯ\n{rubric.strip()}\n"
            if rubric and rubric.strip()
            else ""
        )

        return template.format(
            discipline_suffix=discipline_suffix,
            task_description=task_description.strip(),
            reference_answer=reference_answer.strip(),
            student_answer=student_answer.strip(),
            rubric_block=rubric_block,
        )

    def build_evaluate_retry(self, original_prompt: str, bad_response: str, error: str) -> str:
        """Промпт для retry после неудачной валидации JSON-схемы."""
        return (
            f"{original_prompt}\n\n"
            f"--- ПОВТОРНАЯ ПОПЫТКА ---\n"
            f"Предыдущий ответ не прошёл валидацию по требуемой JSON-схеме.\n"
            f"Ошибка валидации:\n{error}\n\n"
            f"Предыдущий (некорректный) ответ:\n{bad_response[:1500]}\n\n"
            f"Внимательно перечитайте требования к формату выше и верните "
            f"ровно один валидный JSON-объект без markdown, без текста "
            f"до/после, без комментариев. Только JSON."
        )
