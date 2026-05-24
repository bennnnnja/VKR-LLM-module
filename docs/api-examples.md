# API examples

Все `curl`-вызовы ниже подразумевают:

```bash
API=http://localhost:8000
KEY=replace-me-with-strong-random-string   # из .env
```

Все 4 async-эндпоинта возвращают `202 + {jobId}`. Результат —
через `GET /jobs/{jobId}`.

---

## 1. `POST /evaluate/task` — оценка развёрнутого ответа

Модель: `qwen2.5:32b-instruct`. Опционально: постобработка через
`qwen3-embedding:8b` (cosine similarity reference vs student).

### Запрос

```bash
curl -X POST $API/evaluate/task \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "task_text": "Объясните принцип работы виртуальной памяти.",
    "reference_answer": "Виртуальная память — абстракция ОС, дающая процессу плоское адресное пространство; страницы транслируются в физические через таблицы страниц.",
    "student_answer": "Это когда программа думает что у неё много памяти, а на самом деле ОС её эмулирует.",
    "discipline": "Операционные системы",
    "max_score": 100
  }'
```

```json
{"jobId": "62e4adc6-0c3c-41a7-8de5-884eef28630c"}
```

### Ответ `GET /jobs/{jobId}` (после `completed`)

```json
{
  "job_id": "62e4adc6-...",
  "job_type": "evaluate",
  "status": "completed",
  "result": {
    "total_score": 72,
    "criteria": [
      {"name": "Точность",     "score": 75, "comment": "..."},
      {"name": "Полнота",      "score": 65, "comment": "..."},
      {"name": "Логика",       "score": 80, "comment": "..."},
      {"name": "Терминология", "score": 70, "comment": "..."}
    ],
    "summary": "...",
    "strengths": ["Корректная общая идея абстракции"],
    "weaknesses": ["Нет упоминания страниц/таблиц страниц"],
    "similarity": 0.7431
  },
  "llm_log": {
    "target_model": "qwen2.5:32b-instruct",
    "actual_model": "qwen2.5:32b-instruct",
    "model_resolution": "direct",
    "duration_ms": 513,
    "retries": 0,
    "prompt": "...полный собранный промпт...",
    "raw_response": "...как пришло от LLM..."
  }
}
```

Если `max_score != 100`, в `result` добавляется
`scaled_score` и `scaled_max`.

---

## 2. `POST /generate/recommendations` — альтернативные ответы

Модель: `qwen2.5:32b-instruct`. Преподаватель получает N
правдоподобных корректных вариантов студенческого ответа и
выбирает, какие принять как альтернативы эталона.

### Запрос

```bash
curl -X POST $API/generate/recommendations \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "task_description": "Объясните, что такое полиморфизм в ООП, и приведите короткий пример.",
    "max_recommendations": 4,
    "discipline": "Программирование"
  }'
```

### Ответ

```json
{
  "status": "completed",
  "result": {
    "recommendations": [
      {
        "text": "Полиморфизм — способность объектов разных типов отвечать на один и тот же вызов по-разному...",
        "rationale": "Корректное определение через разный отклик на одинаковый интерфейс.",
        "confidence": 0.95
      },
      {
        "text": "Это когда у нескольких классов есть метод с одинаковым именем, но реализация зависит от типа объекта во время выполнения...",
        "rationale": "Подчёркивается динамическая диспетчеризация.",
        "confidence": 0.88
      }
    ]
  },
  "llm_log": { "target_model": "qwen2.5:32b-instruct", "actual_model": "qwen2.5:32b-instruct", "model_resolution": "direct", "..." }
}
```

`max_recommendations`: 1..10. В sandbox — слайдер.

---

## 3. `POST /generate/testcases` — тест-кейсы

Модель: `qwen3-coder-next`. В конфиге предзащиты эта модель
не объявлена доступной, поэтому реально возвращается
**stub-результат**, а в `llm_log.model_resolution` пишется `"stub"`.

### Запрос

```bash
curl -X POST $API/generate/testcases \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"task_text":"Написать функцию add(a:int,b:int)->int","language":"python","count":5}'
```

### Ответ (предзащита, stub)

```json
{
  "status": "completed",
  "result": {
    "cases": [],
    "note": "STUB: qwen3-coder-next недоступна, тест-кейсы не сгенерированы."
  },
  "llm_log": {
    "target_model": "qwen3-coder-next",
    "actual_model": "qwen3-coder-next",
    "model_resolution": "stub",
    "duration_ms": 1000
  }
}
```

В целевой конфигурации (`AVAILABLE_MODELS` содержит
`qwen3-coder-next`) — реальные тест-кейсы (фаза 6+).

---

## 4. `POST /analyze/test-discipline` — классификация дисциплины (async)

Модель: `qwen3:8b`. Сейчас — stub (модель недоступна).

### Запрос

```bash
curl -X POST $API/analyze/test-discipline \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"test_text":"Что такое нормализация баз данных? Назовите три нормальные формы..."}'
```

### Ответ (stub)

```json
{
  "status": "completed",
  "result": {
    "discipline": "unknown",
    "confidence": 0.0,
    "note": "STUB: qwen3:8b недоступна, дисциплина не определена."
  },
  "llm_log": {
    "target_model": "qwen3:8b",
    "model_resolution": "stub"
  }
}
```

---

## 5. `POST /analyze/task-discipline` — классификация (sync)

Единственный синхронный эндпоинт. Без Celery, без `jobId` —
возвращает результат сразу.

### Запрос

```bash
curl -X POST $API/analyze/task-discipline \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"task_text":"Реализовать сортировку слиянием для массива целых чисел."}'
```

### Ответ

```json
{"discipline": "Программирование", "confidence": 0.75}
```

---

## Управление задачами

### `GET /jobs/{jobId}`

```bash
curl $API/jobs/<uuid> -H "X-API-Key: $KEY"
```

`404` — задачи нет (или истёк TTL = 24 часа).

### `POST /jobs/{jobId}/cancel`

```bash
curl -X POST $API/jobs/<uuid>/cancel -H "X-API-Key: $KEY"
```

- `pending` → `cancelled` + `revoke()` в Celery.
- `in_progress` → ставит флаг, воркер останавливается на ближайшей
  проверке (между шагами и перед вызовом Ollama).
- `completed | failed | cancelled` → `409 job_not_cancellable`.

---

## Конфигурация (без секретов)

### `GET /config` (no auth)

```bash
curl $API/config | jq
```

```json
{
  "available_models": ["qwen2.5:32b-instruct"],
  "fallback_strategy": "stub",
  "fallback_model": "qwen2.5:32b-instruct",
  "tasks": {
    "evaluate":        {"target_model": "qwen2.5:32b-instruct", "actual_model": "qwen2.5:32b-instruct", "model_resolution": "direct"},
    "recommendations": {"target_model": "qwen2.5:32b-instruct", "actual_model": "qwen2.5:32b-instruct", "model_resolution": "direct"},
    "testcases":       {"target_model": "qwen3-coder-next",     "actual_model": "qwen3-coder-next",     "model_resolution": "stub"},
    "discipline":      {"target_model": "qwen3:8b",             "actual_model": "qwen3:8b",             "model_resolution": "stub"},
    "embedding":       {"target_model": "qwen3-embedding:8b",   "actual_model": "qwen3-embedding:8b",   "model_resolution": "stub"}
  }
}
```

Используется sandbox-страницей: в шапке показывается общая
конфигурация, в каждой секции — preview резолюции для соответствующей
задачи.

---

## Коды ошибок

| `error.code` | Когда | HTTP |
|---|---|---|
| `unauthorized` | Нет/неверный `X-API-Key` | 401 |
| `job_not_found` | Неизвестный jobId или истёк TTL | 404 |
| `job_not_cancellable` | Job уже в терминальном статусе | 409 |
| `model_unavailable` | `FALLBACK_STRATEGY=fail` и целевая недоступна | внутри Job |
| `llm_invalid_output` | LLM дважды вернула JSON, не проходящий валидацию | внутри Job |
| `llm_timeout` | Ollama не ответила за `LLM_TIMEOUT_SECONDS` | внутри Job |
| `llm_unavailable` | Сетевая ошибка, 4xx/5xx от Ollama | внутри Job |
