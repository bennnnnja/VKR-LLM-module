# API examples

Все `curl`-вызовы ниже подразумевают:

```bash
API=http://localhost:8000
KEY=replace-me-with-strong-random-string   # из .env
```

Все 4 async-эндпоинта возвращают `202 + {jobId}`. Результат —
через `GET /jobs/{jobId}`.

Во всех трёх генерирующих эндпоинтах (`/evaluate/task`,
`/generate/recommendations`, `/generate/testcases`) есть
опциональное поле **`user_prompt`** — произвольные указания
пользователя, которые подмешиваются в промпт перед вызовом LLM.
Они корректируют содержание ответа, но не формат (JSON-схема
остаётся обязательной). При отсутствии поля поведение прежнее.

Все строковые поля в результатах — чистый текст без
markdown-разметки (промпты явно это требуют): фронт отображает
их как plain text.

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
    "max_score": 100,
    "user_prompt": "Будь строже к терминологии, это третий курс."
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
    "discipline": "Программирование",
    "user_prompt": "Хотя бы один вариант — с примером на Python."
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

Модель: `qwen3-coder-next`. Кейсы — «чёрный ящик» (пары
вход → ожидаемый результат), типы `basic | edge | negative`.

### Запрос

```bash
curl -X POST $API/generate/testcases \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{
    "task_description": "Написать функцию add(a: int, b: int) -> int, возвращающую сумму двух целых чисел.",
    "function_signature": "def add(a: int, b: int) -> int",
    "language": "python",
    "count": 5,
    "include_edge_cases": true,
    "include_negative_cases": false,
    "user_prompt": "Добавь кейс с большими числами около границы int64."
  }'
```

`count`: 1..50 (default 10). `function_signature`,
`generation_criteria`, `user_prompt` — опциональные.

### Ответ

```json
{
  "status": "completed",
  "result": {
    "cases": [
      {
        "ordinal_number": 1,
        "description": "Сумма двух положительных чисел",
        "input": "2 3",
        "expected_output": "5",
        "type": "basic"
      },
      {
        "ordinal_number": 2,
        "description": "Сложение с нулём",
        "input": "0 7",
        "expected_output": "7",
        "type": "edge"
      }
    ]
  },
  "llm_log": {
    "target_model": "qwen3-coder-next",
    "actual_model": "qwen3-coder-next",
    "model_resolution": "direct",
    "duration_ms": 8412,
    "retries": 0
  }
}
```

Если модель не объявлена в `AVAILABLE_MODELS`, при
`FALLBACK_STRATEGY=stub` вернётся stub-результат с
`model_resolution: "stub"` и пустым `cases`.

---

## 4. `POST /analyze/task-discipline` — классификация дисциплины (sync)

Единственный синхронный эндпоинт. Без Celery, без `jobId` —
возвращает результат сразу.

Модель — `qwen3:8b`, отдельный таймаут `SYNC_LLM_TIMEOUT_SECONDS=30`
(вместо общих 120 — клиент держит HTTP-соединение открытым всё время
вызова). `discipline` всегда из закрытого списка:
`Программирование | Математика | Русский язык | Литература |
Биология | География | Физика | Прочее`.

### Запрос

```bash
curl -X POST $API/analyze/task-discipline \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"task_text":"Реализовать сортировку слиянием для массива целых чисел."}'
```

### Ответ

```json
{"discipline": "Программирование", "confidence": 0.88}
```

### Коды ошибок (HTTP)

| Код | Когда |
|---|---|
| 200 | Успех |
| 422 | Тело запроса не прошло Pydantic-валидацию |
| 502 | `llm_unavailable` (Ollama не отвечает) или `llm_invalid_output` (LLM дважды вернула невалидный JSON) |
| 503 | `model_unavailable` (при `FALLBACK_STRATEGY=fail`) |
| 504 | `llm_timeout` (вышли за 30 сек) |

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
