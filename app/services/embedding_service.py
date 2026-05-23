from __future__ import annotations

# STUB: появится в фазе 4 — опциональное вычисление косинусной близости
# через qwen3-embedding:8b. Если эмбеддер недоступен, секция similarity
# в результате evaluate_task просто отсутствует.


async def cosine_similarity(reference: str, candidate: str) -> float | None:
    return None
