"""The fixer — Warden's write primitives for fixing an issue.

Three composable steps the brain can stage: create a branch, commit code to it,
and open a pull request. Each is a *write*, so — unlike the read-only explorer —
it never touches GitHub from the agent. The builders here only describe the
writes as ``Action``s; the brain stages them into one proposal, a human approves
it in Slack, and the runner's ``github_repo`` executor performs them in order.

This is not a :class:`~warden_agent.capabilities.base.Capability` (it has no
single ``subject`` and emits no ``ProposalPayload`` on its own); the brain wires
its builders into staging tools — see ``warden_agent.brain.proposing``.
"""
from __future__ import annotations

from . import actions  # noqa: F401

__all__ = ["actions"]
