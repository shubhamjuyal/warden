"""Centralised configuration.

Notice the deliberate split of credentials across two settings objects:

* ``AgentSettings`` carries a **read-only** GitHub token and the OpenAI key.
* ``RunnerSettings`` carries the **write-scoped** GitHub token.

Each process loads only the settings object it needs, and in production each
runs in its own container with its own ``.env``. The agent container is never
given ``GITHUB_WRITE_TOKEN``; the runner container is never given
``GITHUB_READ_TOKEN``. That is the whole point.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://warden:warden@localhost:5432/warden",
        alias="DATABASE_URL",
    )


class AgentSettings(BaseSettings):
    """Loaded inside the sandboxed agent. Read-only credentials only."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://warden:warden@localhost:5432/warden",
        alias="DATABASE_URL",
    )
    # Read-only GitHub token. Even if leaked or prompt-injected, it cannot write.
    github_read_token: str = Field(default="", alias="GITHUB_READ_TOKEN")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    # Where the runner lives. The agent can *ask* this service to act; it cannot
    # act itself.
    runner_url: str = Field(default="http://localhost:8000", alias="RUNNER_URL")

    # Slack (Socket Mode — no public URL required).
    slack_bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    slack_app_token: str = Field(default="", alias="SLACK_APP_TOKEN")

    # Hard guarantee: this string must never be populated in the agent's env.
    # If it ever is, startup fails loudly. See agent/guards.py.
    github_write_token: str = Field(default="", alias="GITHUB_WRITE_TOKEN")


class RunnerSettings(BaseSettings):
    """Loaded inside the permissioned runner. Holds the ONLY write token."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://warden:warden@localhost:5432/warden",
        alias="DATABASE_URL",
    )
    # The single write-scoped credential in the whole system.
    github_write_token: str = Field(default="", alias="GITHUB_WRITE_TOKEN")


@lru_cache
def agent_settings() -> AgentSettings:
    return AgentSettings()


@lru_cache
def runner_settings() -> RunnerSettings:
    return RunnerSettings()


@lru_cache
def db_settings() -> DBSettings:
    return DBSettings()
