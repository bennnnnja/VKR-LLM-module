# Примеры использования API (фаза 1)

Все async-эндпоинты возвращают 202 + jobId; результат опрашивается через
`GET /jobs/{jobId}`. Единственный sync-эндпоинт — `POST /analyze/task-discipline`.

```bash
API=http://localhost:8000
KEY=replace-me-with-strong-random-string
```

## evaluate/task

```bash
JOB=$(curl -s -X POST $API/evaluate/task \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"task_text":"Что такое полиморфизм?","reference_answer":"...","student_answer":"..."}' \
  | jq -r .jobId)

curl -s $API/jobs/$JOB -H "X-API-Key: $KEY" | jq
```

## generate/testcases (фаза 1: stub)

```bash
curl -s -X POST $API/generate/testcases \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"task_text":"Сложить два числа","language":"python","count":3}'
```

В `llm_log.model_resolution` будет `"stub"`, потому что `qwen3-coder-next`
не объявлена в `AVAILABLE_MODELS` для предзащиты.

## cancel

```bash
curl -s -X POST $API/jobs/$JOB/cancel -H "X-API-Key: $KEY"
```

- `pending` → задача отменяется (revoke в Celery + cancel-флаг)
- `in_progress` → ставится cancel-флаг, воркер останавливается на следующей проверке
- `completed | failed | cancelled` → 409
