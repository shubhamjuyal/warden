"""Shared, capability-agnostic wiring for the agent.

Capability-specific collaborators (GitHub readers, classifiers, …) live inside
each capability package. Only things every capability shares belong here — today
that's the client used to *ask* the runner to execute an approved proposal.
"""
from __future__ import annotations

from warden_common.config import agent_settings

from .runner_client import RunnerClient


def build_runner_client() -> RunnerClient:
    return RunnerClient(agent_settings().runner_url)
