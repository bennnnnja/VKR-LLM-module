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

    def build_testcases(
        self,
        task_description: str,
        count: int,
        include_edge_cases: bool,
        include_negative_cases: bool,
        language: Optional[str] = None,
        function_signature: Optional[str] = None,
        generation_criteria: Optional[dict] = None,
    ) -> str:
        template = _load("testcases.txt")

        signature_block = (
            f"\nСИГНАТУРА ФУНКЦИИ\n{function_signature.strip()}\n"
            if function_signature and function_signature.strip()
            else ""
        )

        if generation_criteria:
            import json as _json
            criteria_block = (
                "\nДОПОЛНИТЕЛЬНЫЕ КРИТЕРИИ ГЕНЕРАЦИИ\n"
                f"{_json.dumps(generation_criteria, ensure_ascii=False, indent=2)}\n"
            )
        else:
            criteria_block = ""

        return template.format(
            task_description=task_description.strip(),
            signature_block=signature_block,
            criteria_block=criteria_block,
            count=int(count),
            language=(language or "python").strip(),
            include_edge_cases="true" if include_edge_cases else "false",
            include_negative_cases="true" if include_negative_cases else "false",
        )

    def build_discipline(self, text: str, *, kind: str) -> str:
        """kind: 'тест' либо 'задание' — попадёт в фразу 'текст ({text_kind})'."""
        template = _load("discipline.txt")
        return template.format(
            text=text.strip(),
            text_kind=kind,
        )

    def build_recommendations(
        self,
        task_description: str,
        n: int,
        discipline: Optional[str] = None,
    ) -> str:
        template = _load("recommendations.txt")
        discipline_suffix = (
            f' по дисциплине "{discipline.strip()}"'
            if discipline and discipline.strip()
            else ""
        )
        return template.format(
            discipline_suffix=discipline_suffix,
            task_description=task_description.strip(),
            n=int(n),
        )

    def build_retry(self, original_prompt: str, bad_response: str, error: str) -> str:
        """Универсальный retry-промпт для любой задачи."""
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

    def build_evaluate_retry(self, original_prompt: str, bad_response: str, error: str) -> str:
        # Alias для совместимости с фазой 3 — единая логика retry.
        return self.build_retry(original_prompt, bad_response, error)
