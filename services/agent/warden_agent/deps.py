"""Wiring: build the agent's collaborators from settings, in one place."""
from __future__ import annotations

from warden_common.config import agent_settings

from .classifier import Classifier, LLMClassifier
from .github_read import GitHubReadClient
from .runner_client import RunnerClient


def build_reader() -> GitHubReadClient:
    return GitHubReadClient(agent_settings().github_read_token)


def build_classifier() -> Classifier:
    s = agent_settings()
    return LLMClassifier(api_key=s.openai_api_key, model=s.openai_model)


def build_runner_client() -> RunnerClient:
    return RunnerClient(agent_settings().runner_url)
