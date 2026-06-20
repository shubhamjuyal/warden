"""Pydantic DTOs shared across services.

These describe the *shape of a consequential action* and the proposal that
bundles them. Keeping them here means the agent (which proposes) and the runner
(which executes) agree on exactly one schema, and the audit trail records that
same schema verbatim.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    LABEL = "label"      # apply a label to an issue
    ASSIGN = "assign"    # assign an issue to a user
    CLOSE = "close"      # close an issue (e.g. a confirmed duplicate)


class IssueAction(BaseModel):
    """A single consequential write the agent wants the runner to perform."""

    type: ActionType
    issue_number: int
    # For LABEL -> the label name. For ASSIGN -> the GitHub login. For CLOSE ->
    # the issue number this duplicates (as a string), or "" if not a dup.
    value: str = ""
    rationale: str = Field(..., description="Why the agent proposes this")
    evidence: str = Field(
        default="", description="Quote/signal from the issue supporting it"
    )


class ProposalPayload(BaseModel):
    """The full set of actions the agent proposes for one triage run."""

    repo: str  # "owner/name"
    actions: list[IssueAction]

    def counts(self) -> dict[str, int]:
        out = {t.value: 0 for t in ActionType}
        for a in self.actions:
            out[a.type.value] += 1
        return out

    def summary_line(self) -> str:
        c = self.counts()
        return (
            f"apply {c['label']} labels, assign {c['assign']} issues, "
            f"close {c['close']} duplicates"
        )


# ---- Triage / classification output (agent-internal) -----------------------

Severity = Literal["critical", "high", "medium", "low"]


class IssueClassification(BaseModel):
    issue_number: int
    severity: Severity
    area: str                       # suggested area/team label, e.g. "backend"
    suggested_labels: list[str] = []
    suggested_assignee: str | None = None
    duplicate_of: int | None = None
    rationale: str = ""
    evidence: str = ""


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
    action: IssueAction
    ok: bool
    detail: str = ""


class ExecuteResponse(BaseModel):
    proposal_id: str
    executed: list[ExecutedAction]
    ok: bool
