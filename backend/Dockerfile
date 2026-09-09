FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=1200 \
    PIP_RETRIES=20 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for PDF/table extraction and common scientific wheels runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ghostscript \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.docker.txt /app/requirements.docker.txt
RUN set -eux; \
        for i in 1 2 3 4 5; do \
            pip install --no-cache-dir -r /app/requirements.docker.txt && break; \
            echo "pip install failed (attempt ${i}), retrying..."; \
            sleep $((i * 5)); \
        done

COPY backend /app/backend

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
