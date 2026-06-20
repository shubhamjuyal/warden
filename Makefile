.PHONY: help install test up down logs demo-cli fmt clean

help:
	@echo "Warden — make targets:"
	@echo "  make install   create a venv and install all three Python packages + pytest"
	@echo "  make test      run the test suite (incl. the guardrail-bypass tests)"
	@echo "  make up        docker compose up --build (postgres, runner, agent, dashboard)"
	@echo "  make down      stop and remove containers"
	@echo "  make logs      tail all container logs"
	@echo "  make demo-cli  run the headless triage->approve->execute loop (needs .env)"

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -U pip && \
		pip install -e services/common -e services/runner -e services/agent pytest

test:
	. .venv/bin/activate && python -m pytest

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

# Headless walkthrough without Slack. Requires .env (GITHUB_READ_TOKEN,
# OPENAI_API_KEY) and the runner running (make up, or run it separately).
demo-cli:
	. .venv/bin/activate && warden triage $(REPO)

clean:
	rm -rf .venv dashboard/node_modules dashboard/.next
