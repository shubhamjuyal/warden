"""Platform-core DTOs shared across services.

These are deliberately capability-agnostic. A **capability** (triage today;
others later) produces a ``ProposalPayload`` — a bundle of consequential
``Action``s. Each action names the **provider** that should execute it, so the
runner can dispatch to the right executor without knowing anything about the
capability that proposed it. The same proposal/approval/audit machinery serves
every capability.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Action(BaseModel):
    """A single consequential write a capability wants performed.

    Provider-agnostic by design: ``provider`` selects the runner-side executor,
    ``type`` is the operation within that provider, and ``target`` identifies the
    object it applies to. A new capability reuses this shape — it does not invent
    a new action schema.
    """

    provider: str  # which runner executor performs this, e.g. "github_issues"
    type: str      # operation within the provider, e.g. "label" | "assign" | "close"
    target: str    # the object the action applies to, e.g. an issue number
    value: str = ""
    rationale: str = Field(..., description="Why the agent proposes this")
    evidence: str = Field(
        default="", description="Quote/signal supporting it"
    )


class ProposalPayload(BaseModel):
    """The full set of actions one capability run proposes."""

    capability: str  # which capability produced this, e.g. "triage"
    subject: str     # human-readable scope, e.g. "acme/api"
    actions: list[Action]

    def counts(self) -> dict[str, int]:
        """Count actions by type — works for any capability's action mix."""
        out: dict[str, int] = {}
        for a in self.actions:
            out[a.type] = out.get(a.type, 0) + 1
        return out

    def summary_line(self) -> str:
        """Generic one-liner. A capability may render a nicer summary of its own
        (see ``Capability.summarize``)."""
        if not self.actions:
            return "no actions"
        return ", ".join(f"{n} {t}" for t, n in self.counts().items())


# ---- Runner request / response ---------------------------------------------

DecisionType = Literal["approve_once", "approve", "deny", "standing_rule"]


class ExecuteRequest(BaseModel):
    """What the agent POSTs to the runner. Note it carries NO credentials and
    NO action list — only identifiers. The runner re-reads the authoritative
    proposal + approval from the ledger so a compromised agent cannot smuggle
    in extra actions."""

    proposal_id: str
    approval_token: str


class ExecutedAction(BaseModel):
    action: Action
    ok: bool
    detail: str = ""


class ExecuteResponse(BaseModel):
    proposal_id: str
    executed: list[ExecutedAction]
    ok: bool
