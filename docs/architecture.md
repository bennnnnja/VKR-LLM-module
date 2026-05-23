# Архитектура (фаза 1)

Сервис состоит из трёх процессов:

- **api** (FastAPI / uvicorn) — принимает HTTP-запросы, создаёт Job
  в Redis, ставит задачу в очередь Celery, отвечает 202 + jobId.
- **worker** (Celery) — забирает задачу, проходит через ModelRouter,
  выполняет реальный вызов LLM (фазы 3-4) или возвращает stub-результат,
  записывает llm_log и результат обратно в Redis.
- **redis** — брокер Celery, result backend Celery, хранилище Job.

```
client ──HTTP──▶ api ──Celery enqueue──▶ broker (redis) ──▶ worker ──┐
   ▲                                                                  │
   └────── poll GET /jobs/{id} ◀────── job store (redis) ◀────────────┘
```

Жизненный цикл Job:

```
pending ──▶ in_progress ──▶ completed
                       │
                       └─▶ failed
            │
            └─▶ cancelled (на любом из шагов до завершения)
```

ModelRouter изолирует решение «вызывать ли модель или вернуть stub» от
бизнес-логики воркера, так что добавление новых моделей в `AVAILABLE_MODELS`
не требует правок кода.

См. также:
- `app/services/model_router.py` — алгоритм выбора модели
- `app/workers/_runner.py` — общий каркас Celery-задачи
- `app/services/job_store.py` — хранилище Job в Redis
