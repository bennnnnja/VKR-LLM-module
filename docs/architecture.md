# Архитектура

## Назначение

Сервис автоматизированного оценивания учебных работ открытого
типа. Принимает текстовые задания и ответы, прогоняет через
специализированные LLM (Qwen) и возвращает структурированные
результаты: оценку по критериям, альтернативные правильные ответы,
тест-кейсы, классификацию дисциплины.

## Стек

Python 3.11+ · FastAPI · Celery · Redis (брокер + result backend
+ хранилище Job) · httpx · Pydantic v2 · loguru · Ollama API.

## Топология процессов

```
                  ┌──────────────────────────────────────────┐
client ─HTTP─▶    │   api (FastAPI / uvicorn)                │
   ▲              │   - принимает запрос                     │
   │              │   - создаёт Job в Redis                  │
   │              │   - ставит таск в очередь Celery         │
   │              │   - отвечает 202 + jobId                 │
   │              └──────────────────────────────────────────┘
   │                              │
   │                              ▼  Celery enqueue
   │                  ┌────────────────────────┐
   │                  │   redis (брокер +       │
   │                  │   result backend +      │
   │                  │   job store)            │
   │                  └────────────────────────┘
   │                              │
   │                              ▼  prefetch by worker
   │              ┌──────────────────────────────────────────┐
   │              │   worker (Celery)                        │
   │              │   - читает Job из стора                  │
   │              │   - ModelRouter.resolve(target_model)   │
   │              │   - реальный вызов Ollama или stub      │
   │              │   - 1 retry на невалидный JSON          │
   │              │   - опциональный postprocess (similarity)│
   │              │   - сохраняет result + llm_log          │
   │              └──────────────────────────────────────────┘
   │                              │
   │                              ▼
   └────── poll GET /jobs/{id} ◀──┘
```

## Типизированный пайплайн моделей (ключевое решение)

Архитектурное решение, зафиксированное в дипломе: разные задачи
обслуживаются разными специализированными моделями, а не одной
универсальной. Это даёт лучшее качество per-task и предотвращает
переусложнение промптов.

| Задача                         | Модель                | Метод вызова |
|--------------------------------|-----------------------|--------------|
| Оценка ответа + рекомендации   | `qwen2.5:32b-instruct` | `/api/generate` |
| Альтернативные ответы          | `qwen2.5:32b-instruct` | `/api/generate` |
| Генерация тест-кейсов          | `qwen3-coder-next`    | `/api/generate` |
| Классификация дисциплины       | `qwen3:8b`            | `/api/generate` |
| Семантическое сравнение        | `qwen3-embedding:8b`  | `/api/embeddings` |

### Стратегия резолюции моделей (`ModelRouter`)

В каждый момент в окружении доступен не весь набор. `ModelRouter`
решает, что делать с задачей, нацеленной на недоступную модель:

| `FALLBACK_STRATEGY` | целевая доступна | целевая недоступна |
|---|---|---|
| `stub` (default для предзащиты) | `direct` | `stub` |
| `fallback` | `direct` | `fallback` на `FALLBACK_MODEL`, иначе `fail` |
| `fail` (целевой режим для финальной ВКР) | `direct` | `fail` (`error.code=model_unavailable`) |

Каждое решение пишется в `Job.llm_log.model_resolution`. В UI
sandbox видно: целевая модель, фактическая модель, режим резолюции
— это даёт комиссии прозрачность «какой моделью реально оценена
работа».

### Переключение конфигураций

Предзащита:
```
AVAILABLE_MODELS=qwen2.5:32b-instruct
FALLBACK_STRATEGY=stub
```
Реально доступна одна модель, остальные задачи возвращают
зафиксированный stub-результат, чтобы UI и API-контракт оставались
полностью функциональными.

Финальная ВКР:
```
AVAILABLE_MODELS=qwen2.5:32b-instruct,qwen3-coder-next,qwen3:8b,qwen3-embedding:8b
FALLBACK_STRATEGY=fail
```
Все модели доступны, любая попытка вызвать что-то неожиданное
падает быстро вместо тихой подмены. Код не меняется — меняется
конфиг.

## Жизненный цикл задачи

```
pending ──▶ in_progress ──▶ completed
                       │
                       └──▶ failed
            │
            └──▶ cancelled  (на любом из шагов до завершения)
```

- `pending` — Job создан, поставлен в очередь Celery.
- `in_progress` — воркер подхватил, начал работу.
- `completed` — успех, есть `result` и заполненный `llm_log`.
- `failed` — есть `error` с `code ∈ {model_unavailable,
  llm_invalid_output, llm_unavailable, llm_timeout}`.
- `cancelled` — отменено клиентом через `POST /jobs/{id}/cancel`.

Все статусы хранятся в Redis с TTL = `JOB_TTL_SECONDS`
(default 24 часа).

## Ограничения нагрузки на корпоративную LLM-инфраструктуру

GPU-сервер Ollama в ДВФУ используется другими командами. Цель —
гарантировать, что наш сервис не создаёт всплесков нагрузки.
Три уровня:

1. **Concurrency-лимит в HTTP-клиенте.** `OllamaClient` внутри
   держит `asyncio.Semaphore(LLM_MAX_CONCURRENT)` (default 2).
   Не более N одновременных физических вызовов внутри процесса.
2. **Жёсткий таймаут.** `httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS)`
   (default 120с). Превышение → `error.code=llm_timeout`.
3. **Celery worker_concurrency.** Воркер стартует с явными
   `--concurrency=$CELERY_WORKER_CONCURRENCY --prefetch-multiplier=$CELERY_PREFETCH_MULTIPLIER`
   (default 2/1).

Все три параметра — в `.env.example`.

## Структурированный вывод LLM (двухуровневая валидация)

1. Ollama `format=json` + жёсткая инструкция о схеме в промпте.
2. Pydantic-валидация ответа (`EvaluateLLMOutput`,
   `RecommendationsLLMOutput`, ...).
3. При невалидном ответе — **1 retry** с промптом-уточнением
   («предыдущий ответ не прошёл валидацию по схеме X, ошибка Y,
   верни корректный JSON»).
4. После повторной неудачи — `failed`, `error.code=llm_invalid_output`.

## Ключевые модули

| Модуль | Ответственность |
|---|---|
| `app/services/model_router.py` | Стратегия выбора модели для задачи |
| `app/services/llm_client.py` | Async httpx-клиент к Ollama, семафор, таймауты, кастомные `LLMTimeout`/`LLMUnavailable` |
| `app/services/embedding_service.py` | Эмбеддинги + косинусная близость; ошибки → `None`, без падений |
| `app/services/job_store.py` | CRUD по Job в Redis (async для API + sync для Celery) |
| `app/services/prompt_builder.py` | Сборка промптов из `app/prompts/*.txt` |
| `app/workers/_llm_runner.py` | Общий async-каркас для всех LLM-задач: cancel-чек, ModelRouter, stub/fail/direct/fallback, retry, postprocess |
| `app/workers/_async_bridge.py` | sync→async-мост для Celery-таска: обычный `asyncio.run` или fresh thread, если loop уже работает (тесты) |
| `app/workers/{evaluate,recommendations,testcases,discipline_test}_task.py` | Тонкие фасады над `_llm_runner`: подсовывают prompt-builder, output-схему и (для evaluate) postprocess |
| `app/middleware/auth.py` | Проверка `X-API-Key`, публичный allowlist для `/health`, `/config`, `/sandbox`, `/ui-kit`, `/static`, `/docs` |
| `app/static/sandbox.html` | UI-витрина с пятью секциями + автополлинг + просмотр `llm_log` |
| `app/static/components/*.js` | Ванильные Web Components (job-poller, evaluate-form, recommendations-list) |

## Аутентификация

`X-API-Key` в заголовке. Ключ из env `API_KEY`. Не применяется к
`/health`, `/config`, `/sandbox`, `/ui-kit`, `/static/*`, `/docs`,
`/redoc`, `/openapi.json`, `/` (редирект).
