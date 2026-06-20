"""Test fixtures: a throwaway SQLite ledger per test, plus fakes for the
external services (GitHub read/write, OpenAI). No network, no live tokens."""
from __future__ import annotations

import os

import pytest

from warden_common import config as cfg
from warden_common.db import init_engine


@pytest.fixture()
def ledger_db(tmp_path, monkeypatch):
    """Point every settings object at a fresh file-backed SQLite ledger."""
    url = f"sqlite:///{tmp_path}/warden_test.db"
    monkeypatch.setenv("DATABASE_URL", url)
    # Settings are cached with lru_cache; clear so the new env is picked up.
    cfg.db_settings.cache_clear()
    cfg.agent_settings.cache_clear()
    cfg.runner_settings.cache_clear()
    init_engine(url, create_all=True)
    yield url
