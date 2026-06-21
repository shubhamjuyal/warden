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

from warden_common import ledger
from warden_common.db import session_scope

from .. import capabilities
from ..capabilities.base import Capability
from ..surfaces.cards import proposal_blocks
from .context import current_turn


def _run_capability(capability: Capability, subject: str) -> str:
    """Tool body: read-only reasoning -> proposal -> approval card in-thread."""
    ctx = current_turn()
    subject = (subject or "").strip()
    if not subject:
        # Defensive: the prompt tells the model to ask first, but never act on a
        # blank subject if it slips through.
        return (
            f"I can't run {capability.name} without a subject "
            f"({capability.subject_description}). Ask the user for it."
        )

    payload = capability.run(subject=subject, requested_by=ctx.user)
    if not payload.actions:
        return (
            f"Ran {capability.name} on {subject}: nothing to propose — no actions "
            f"needed. Tell the user there's nothing to do."
        )

    with session_scope() as session:
        proposal = ledger.create_proposal(
            session, payload=payload, requested_by=ctx.user, slack_channel=ctx.channel
        )
        proposal_id = proposal.id

    summary = capability.summarize(payload)
    ctx.say(
        blocks=proposal_blocks(proposal_id, payload, summary),
        text="Warden proposal",
        thread_ts=ctx.thread_ts,
    )
    return (
        f"Proposed for {subject}: {summary}. I posted an approval card in the "
        f"thread (proposal {proposal_id[:8]}). Tell the user to review and "
        f"Approve/Deny — nothing happens until they do."
    )


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
    """One tool per registered capability — the agent's entire action surface."""
    return [_build_tool(cap) for cap in capabilities.all_capabilities()]
