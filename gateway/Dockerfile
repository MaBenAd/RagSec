FROM python:3.12.14-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-security.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-security.lock && \
    useradd --uid 10001 --create-home ragsec && mkdir -p /app/backend/data/logs /ipc /staging && \
    chown -R 10001:10001 /app /ipc /staging
COPY --chown=10001:10001 backend backend
COPY --chown=10001:10001 gateway gateway
COPY --chown=10001:10001 rag rag
COPY --chown=10001:10001 scanners scanners
USER 10001:10001
CMD ["uvicorn", "gateway.runtime:application", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
