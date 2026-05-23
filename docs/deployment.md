# Развёртывание

## Локально (Docker Compose)

```bash
cp .env.example .env
# отредактируй API_KEY и OLLAMA_BASE_URL под своё окружение
docker compose up --build
```

Поднимется три контейнера:
- `redis` — порт 6379
- `api` — порт 8000
- `worker` — без проброса портов, читает очередь из redis

Проверка:
```bash
curl http://localhost:8000/health
```

## Конфигурация для предзащиты

```
AVAILABLE_MODELS=qwen2.5:32b-instruct
FALLBACK_STRATEGY=stub
```

С этим конфигом физически вызывается только qwen2.5:32b-instruct
(в фазах 3-4), остальные модели возвращают stub-результат.

## Конфигурация для финальной ВКР

После получения доступа ко всем моделям в корпоративном Ollama:

```
AVAILABLE_MODELS=qwen2.5:32b-instruct,qwen3-coder-next,qwen3:8b,qwen3-embedding:8b
FALLBACK_STRATEGY=fail
```

Код менять не нужно — только конфиг.
