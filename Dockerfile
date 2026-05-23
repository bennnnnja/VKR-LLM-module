FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.32.0" \
        "celery>=5.4.0" \
        "redis>=5.2.0" \
        "httpx>=0.27.0" \
        "pydantic>=2.9.0" \
        "pydantic-settings>=2.6.0" \
        "loguru>=0.7.0" \
        "python-multipart>=0.0.12"

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
