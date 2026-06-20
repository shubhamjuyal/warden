"""Capability base class + registry.

A **capability** is one thing Warden can do end-to-end on the agent side: given a
subject (e.g. a repo), it reasons and returns a ``ProposalPayload`` of
consequential actions for a human to approve. Triage is the first capability.

Adding another is intentionally small:

    from ..base import Capability, register

    class ReleaseNotesCapability(Capability):
        name = "release-notes"
        help = "Summarise merged PRs since the last tag. Usage: release-notes <owner/repo>"
        def run(self, *, subject, requested_by):
            ...
            return ProposalPayload(capability=self.name, subject=subject, actions=[...])

    register(ReleaseNotesCapability())

The Slack and CLI surfaces pick capabilities up from the registry automatically —
no surface code changes needed to ship a new one.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from warden_common.schemas import ProposalPayload


class Capability(ABC):
    #: command keyword, e.g. "triage" (what users type after @warden / on the CLI)
    name: str = ""
    #: one-line help shown when listing capabilities
    help: str = ""

    @abstractmethod
    def run(self, *, subject: str, requested_by: str) -> ProposalPayload:
        """Do the read-only reasoning and return a proposal. Must NOT write."""
        ...

    def summarize(self, payload: ProposalPayload) -> str:
        """Human summary for the Slack approval card. Override for nicer copy."""
        return payload.summary_line()


_REGISTRY: dict[str, Capability] = {}


def register(capability: Capability) -> None:
    if not capability.name:
        raise ValueError("capability must define a non-empty name")
    _REGISTRY[capability.name] = capability


def get(name: str) -> Capability | None:
    return _REGISTRY.get(name)


def all_capabilities() -> list[Capability]:
    return list(_REGISTRY.values())


def names() -> list[str]:
    return list(_REGISTRY)
