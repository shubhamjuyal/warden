"""The explorer's collaborators, built from settings.

Mirrors ``triage/deps.py``: a single read-only GitHub client built from the
agent's read token. Using ``github_read_token`` only is what keeps the explorer
inside the sandbox — there is no write credential anywhere in this package.
"""
from __future__ import annotations

from warden_common.config import agent_settings

from .repo_reader import GitHubRepoReader


def build_repo_reader() -> GitHubRepoReader:
    return GitHubRepoReader(agent_settings().github_read_token)
