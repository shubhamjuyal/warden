"""Triage's collaborators, built from settings.

These are triage-specific (a GitHub reader, an OpenAI classifier). Other
capabilities build their own. Shared, capability-agnostic wiring (e.g. the
runner client) lives in ``warden_agent.deps``.
"""
from __future__ import annotations

from warden_common.config import agent_settings

from .classifier import Classifier, LLMClassifier
from .github_read import GitHubReadClient


def build_reader() -> GitHubReadClient:
    return GitHubReadClient(agent_settings().github_read_token)


def build_classifier() -> Classifier:
    s = agent_settings()
    return LLMClassifier(api_key=s.openai_api_key, model=s.openai_model)
