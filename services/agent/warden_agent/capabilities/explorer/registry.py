"""A registry for read-only tools — deliberately parallel to the capability
registry, never mixed with it.

A :class:`~warden_agent.capabilities.base.Capability` *proposes* consequential
actions: it returns a ``ProposalPayload`` that both surfaces (Slack and the CLI)
turn into an approval flow. A read-only tool does no such thing — it reads
GitHub and answers in the thread, with nothing to approve. Keeping the two in
separate registries means the capability path (and its guardrails) stays exactly
as it is, while the brain can still offer both kinds of tools side by side.
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool

_READONLY_TOOLS: dict[str, StructuredTool] = {}


def register_readonly(tool: StructuredTool) -> None:
    if not tool.name:
        raise ValueError("read-only tool must define a non-empty name")
    _READONLY_TOOLS[tool.name] = tool


def all_readonly_tools() -> list[StructuredTool]:
    return list(_READONLY_TOOLS.values())
