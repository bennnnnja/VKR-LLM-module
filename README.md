# LLM Grading Service

Микросервис автоматизированного оценивания учебных работ открытого
типа на основе LLM. Бакалаврская ВКР, ДВФУ.

Сервис принимает текстовые задания и развёрнутые ответы студентов,
прогоняет их через специализированные модели Qwen в корпоративном
Ollama ДВФУ и возвращает структурированные результаты: оценку
с критериями, набор корректных альтернативных ответов, тест-кейсы,
классификацию дисциплины.

## Ключевая идея — типизированный пайплайн моделей

Не одна универсальная модель, а четыре специализированные:

| Задача                         | Модель                |
|--------------------------------|-----------------------|
| Оценка ответа                  | `qwen2.5:32b-instruct` |
| Альтернативные ответы          | `qwen2.5:32b-instruct` |
| Генерация тест-кейсов          | `qwen3-coder-next`    |
| Классификация дисциплины       | `qwen3:8b`            |
| Семантическое сравнение        | `qwen3-embedding:8b`  |

Если целевая модель сейчас не доступна — `ModelRouter` либо
возвращает stub, либо подменяет на fallback, либо валит задачу с
`model_unavailable`. Поведение управляется одной переменной
окружения `FALLBACK_STRATEGY` без правок кода.

## Быстрый старт

```bash
git clone <repo> && cd VKR-LLM-module
cp .env.example .env       # отредактируй API_KEY и OLLAMA_BASE_URL
docker compose up --build
```

Открой в браузере:

- **<http://localhost:8000/>** → редирект на sandbox
- **<http://localhost:8000/sandbox>** — UI для дёргания всех эндпоинтов
  с визуализацией жизненного цикла задачи и `llm_log`
- **<http://localhost:8000/ui-kit>** — витрина Web Components
- **<http://localhost:8000/docs>** — OpenAPI
- **<http://localhost:8000/health>** — health-check
- **<http://localhost:8000/config>** — текущая конфигурация моделей и
  preview резолюции для каждой задачи

В sandbox в шапке вводится `X-API-Key` — он сохраняется в
`localStorage` и автоматически прикладывается ко всем запросам.

## Эндпоинты

| Метод | Путь                          | Тип   | Модель |
|-------|-------------------------------|-------|--------|
| POST  | `/evaluate/task`              | async | qwen2.5:32b-instruct |
| POST  | `/generate/recommendations`   | async | qwen2.5:32b-instruct |
| POST  | `/generate/testcases`         | async | qwen3-coder-next |
| POST  | `/analyze/task-discipline`    | sync  | qwen3:8b |
| GET   | `/jobs/{jobId}`               | sync  | — |
| POST  | `/jobs/{jobId}/cancel`        | sync  | — |

Async-эндпоинты возвращают `202 + {jobId}`, результат опрашивается
через `GET /jobs/{jobId}` до статуса
`completed | failed | cancelled`.

Подробные примеры запросов и ответов — в [`docs/api-examples.md`](docs/api-examples.md).

## Документация

- [`docs/architecture.md`](docs/architecture.md) — архитектура,
  типизированный пайплайн, жизненный цикл задачи, ограничения
  нагрузки на LLM-инфраструктуру.
- [`docs/api-examples.md`](docs/api-examples.md) — `curl`-примеры
  каждого эндпоинта с примером ответа.
- [`docs/deployment.md`](docs/deployment.md) — пошаговая инструкция
  запуска (Docker Compose, локальный Python, конфигурация для
  предзащиты и для финальной ВКР).

## Стек

Python 3.11+ · FastAPI · Celery · Redis · httpx · Pydantic v2 ·
loguru · Ollama API · Web Components (ваниль, без сборки).

## Тесты

```bash
pytest -v
```

58+ тестов: ModelRouter (все 4 стратегии), полный жизненный цикл
async-задач, OllamaClient через `httpx.MockTransport` с тестом
семафора, валидация JSON-схем, retry-логика, постобработка через
embedder, sandbox/ui-kit публичность.
