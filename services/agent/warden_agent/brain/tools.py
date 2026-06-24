"""Turn the capability registry into LangChain tools for the agent.

Each registered :class:`~warden_agent.capabilities.base.Capability` becomes exactly
one tool the brain can call: its ``name`` and ``help`` become the tool's name and
description (what the model routes on), and its ``subject_description`` describes the
single ``subject`` argument the model must extract from the conversation.

Invoking a tool reuses the exact read-only flow the old Slack handler had: run the
capability, persist the resulting proposal in the ledger, and post an approval card
into the Slack thread. The tool then returns a short confirmation the model relays
to the user. The brain never writes to GitHub — it only proposes; a human still
approves in Slack and the runner still executes. (This module deliberately imports
no write path and never touches ``warden_runner``.)
"""
from __future__ import annotations

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .. import capabilities
from ..capabilities.base import Capability
from ..capabilities.explorer.registry import all_readonly_tools
from .context import current_turn
from .proposing import build_write_tools, post_proposal


def _run_capability(capability: Capability, subject: str) -> str:
    """Tool body: read-only reasoning -> proposal -> approval card in-thread."""
    ctx = current_turn()
    subject = (subject or "").strip()
    if not subject:
        # Defensive: the prompt tells the model to ask first, but never act on a
        # blank subject if it slips through.
        return f"{capability.name} needs a subject: {capability.subject_description}"

    payload = capability.run(subject=subject, requested_by=ctx.user)
    if not payload.actions:
        return f"{capability.name} on {subject}: nothing to propose."

    return post_proposal(payload, capability.summarize(payload))


def _args_schema(capability: Capability) -> type[BaseModel]:
    """A one-field ``{subject}`` schema, described per capability for the model."""
    return create_model(
        f"{capability.name.replace('-', '_').title()}Args",
        subject=(str, Field(description=capability.subject_description)),
    )


def _build_tool(capability: Capability) -> StructuredTool:
    return StructuredTool.from_function(
        func=lambda subject, _cap=capability: _run_capability(_cap, subject),
        name=capability.name,
        description=capability.help,
        args_schema=_args_schema(capability),
    )


def build_tools() -> list[StructuredTool]:
    """The agent's entire tool surface:

    * one approval-producing tool per registered capability (e.g. triage),
    * the explorer's read-only repository tools (answer directly, never propose),
    * the fixer's write tools (stage branch/commit/PR, then submit one approval).
    """
    proposal_tools = [_build_tool(cap) for cap in capabilities.all_capabilities()]
    return proposal_tools + all_readonly_tools() + build_write_tools()
