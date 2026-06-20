FROM python:3.11-slim

WORKDIR /app

# Install the shared package first (separate layer for caching), then the runner.
COPY services/common /app/common
COPY services/runner /app/runner

RUN pip install --no-cache-dir /app/common && \
    pip install --no-cache-dir /app/runner

EXPOSE 8000

# This container is the ONLY one that should ever receive GITHUB_WRITE_TOKEN.
CMD ["uvicorn", "warden_runner.app:app", "--host", "0.0.0.0", "--port", "8000"]
