# Развёртывание

## Способ 1 — Docker Compose (рекомендуется)

### Требования
- Docker Engine 24+
- Docker Compose v2
- Доступ к корпоративной сети ДВФУ (для доступа к Ollama)

### Шаги

```bash
git clone <repo> && cd VKR-LLM-module
cp .env.example .env
# отредактируй .env:
#   API_KEY=<длинная случайная строка>
#   OLLAMA_BASE_URL=http://<хост-ollama-вкр-дальневосточного>:11434
docker compose up --build
```

Поднимется три контейнера:
- `redis` — порт 6379
- `api` — порт 8000 (uvicorn)
- `worker` — без проброса портов (Celery, читает очередь из Redis)

Проверка:

```bash
curl http://localhost:8000/health           # → {"status":"ok"}
xdg-open http://localhost:8000/sandbox      # UI для дёргания всех ручек
```

Остановить:

```bash
docker compose down
```

Очистить вместе с volume Redis:

```bash
docker compose down -v
```

---

## Способ 2 — Локальный Python (для отладки)

### Требования
- Python 3.11+
- Redis (нативный или в Docker — см. ниже)

### Установка Redis

```bash
# macOS
brew install redis && brew services start redis

# Ubuntu / Debian / WSL
sudo apt-get install -y redis-server
sudo systemctl enable --now redis-server

# В Docker (без полного compose)
docker run -d --name redis-vkr -p 6379:6379 redis:7-alpine
```

Проверка: `redis-cli ping` → `PONG`.

### Запуск приложения

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# отредактируй .env:
#   REDIS_URL=redis://localhost:6379/0      (вместо redis://redis:6379/0)
#   API_KEY=<длинная случайная строка>
#   OLLAMA_BASE_URL=<...>
```

Три терминала:

```bash
# терминал 1 — API
uvicorn app.main:app --reload --port 8000

# терминал 2 — Celery worker
# Linux/macOS:
celery -A app.workers.celery_app worker --concurrency=2 --prefetch-multiplier=1 --loglevel=info
# Windows (prefork сломан, используем solo-pool):
celery -A app.workers.celery_app worker --pool=solo --loglevel=info

# терминал 3 — Redis (если не запущен как сервис)
redis-server
```

---

## Конфигурация моделей

### Для предзащиты (только qwen2.5:32b-instruct)

```
AVAILABLE_MODELS=qwen2.5:32b-instruct
FALLBACK_STRATEGY=stub
```

Реально вызываются evaluate и recommendations. Остальные задачи
возвращают зафиксированный stub-результат с пометкой
`model_resolution=stub` в `llm_log` — sandbox это явно показывает.

### Для финальной ВКР (все модели доступны)

```
AVAILABLE_MODELS=qwen2.5:32b-instruct,qwen3-coder-next,qwen3:8b,qwen3-embedding:8b
FALLBACK_STRATEGY=fail
```

Любая попытка дёрнуть задачу с моделью, которой нет в списке,
быстро упадёт с `error.code=model_unavailable` вместо тихой
подмены.

**Код не меняется** — меняется только `.env`.

---

## Параметры нагрузки на Ollama

```
LLM_MAX_CONCURRENT=2              # семафор внутри OllamaClient
LLM_TIMEOUT_SECONDS=120           # httpx timeout
CELERY_WORKER_CONCURRENCY=2       # сколько таскам подхватывать одновременно
CELERY_PREFETCH_MULTIPLIER=1      # не «жадничать» в очереди
```

Эти три значения работают вместе: на одного воркера —
`CELERY_WORKER_CONCURRENCY` параллельных тасков, каждый из которых
делает не более `LLM_MAX_CONCURRENT` одновременных вызовов в
Ollama, и каждый отдельный вызов жёстко ограничен
`LLM_TIMEOUT_SECONDS`.

---

## Тесты

```bash
pip install -r requirements.txt   # включая dev-зависимости
pytest -v
```

58+ тестов прогоняются за <1 секунды (fakeredis вместо настоящего
Redis, Celery в eager-mode, OllamaClient заменён на
`FakeOllamaClient`).

---

## Логи

По умолчанию формат читаемый (для разработки и демо):

```
12:34:56 | INFO  | Target model: qwen2.5:32b-instruct, resolution: direct
12:34:56 | INFO  | Calling Ollama (model=qwen2.5:32b-instruct, prompt=1318b, in-flight=1/2)
12:34:57 | INFO  | Generation took 0.5s, 287 tokens
12:34:57 | INFO  | Computing similarity via qwen3-embedding:8b
12:34:57 | INFO  | Similarity = 0.7431
```

Для прода с агрегатором логов:

```
LOG_FORMAT=json
LOG_LEVEL=INFO
```

— тогда каждая строка — одно JSON-сообщение.

---

## Траблшутинг

### Celery воркер падает на Windows с `WinError 5`

Известная проблема: на Windows стандартный `prefork`-pool через
billiard не работает корректно с семафорами Windows. Используй
`--pool=solo` (см. выше).

### `Connection refused` при обращении к Ollama

Проверь:
1. Включён ли VPN (Ollama в корпоративной сети ДВФУ).
2. Доступен ли хост: `curl <OLLAMA_BASE_URL>/api/tags`.
3. Совпадает ли `OLLAMA_BASE_URL` в `.env`.

В sandbox задача с такой проблемой завершится статусом `failed`
с `error.code=llm_unavailable` — это ожидаемое поведение.

### Job застрял в `pending`

Проверь, что воркер запущен и видит задачу:

```bash
docker compose logs worker
# или
celery -A app.workers.celery_app inspect active
```
