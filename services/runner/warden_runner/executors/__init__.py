"""Provider executors — the runner's pluggable write surface.

Each capability's actions name a ``provider``. The runner looks the provider up
in a :class:`Registry` and asks it to perform the action. Adding write support
for a new capability is: write a ``ProviderExecutor``, register it here. The
generic gate in ``app.py`` does not change.
"""
from __future__ import annotations

from .base import ProviderExecutor, Registry, execute_proposal
from .github_issues import GithubIssuesExecutor, Writer
from .github_repo import GithubRepoExecutor, RepoWriter

__all__ = [
    "ProviderExecutor",
    "Registry",
    "execute_proposal",
    "GithubIssuesExecutor",
    "GithubRepoExecutor",
    "Writer",
    "RepoWriter",
    "build_default_registry",
]


def build_default_registry(github_writer: Writer) -> Registry:
    """Wire up the executors shipped with Warden today.

    To add a capability that writes somewhere new, construct its executor (with
    whatever credential it needs) and ``register`` it here. The write token for
    each provider lives only in the runner — never in the agent.

    ``GitHubWriteClient`` implements both the issues and repo write surfaces, so
    the same writer backs both GitHub executors.
    """
    registry = Registry()
    registry.register(GithubIssuesExecutor(github_writer))
    registry.register(GithubRepoExecutor(github_writer))
    return registry
