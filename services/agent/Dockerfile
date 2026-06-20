FROM python:3.11-slim

WORKDIR /app

COPY services/common /app/common
COPY services/agent /app/agent

RUN pip install --no-cache-dir /app/common && \
    pip install --no-cache-dir /app/agent

# This container must NEVER be given GITHUB_WRITE_TOKEN. guards.assert_sandboxed()
# crashes the process on startup if it is, turning misconfig into a loud failure.
CMD ["python", "-m", "warden_agent.slack_app"]
