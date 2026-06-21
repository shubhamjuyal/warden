"""Turn triage classifications into a generic ``ProposalPayload``.

This is where the triage capability maps its internal reasoning onto the
platform's provider-agnostic ``Action`` shape. Every action it emits names the
``github_issues`` provider, which the runner knows how to execute.

Triage proposes two kinds of action per issue: apply its single label, and (when
the model picked a valid collaborator) assign it.
"""
from __future__ import annotations

from warden_common.schemas import Action, ProposalPayload

from .types import IssueClassification

PROVIDER = "github_issues"


def build_payload(
    subject: str,
    classifications: list[IssueClassification],
    valid_assignees: list[str] | None = None,
) -> ProposalPayload:
    # When we know the assignable collaborators, drop any assignee outside that
    # set as a guard against the model inventing one. If we couldn't fetch the
    # list, trust the model's choice.
    allowed = set(valid_assignees) if valid_assignees else None

    actions: list[Action] = []
    for c in classifications:
        target = str(c.issue_number)
        # 1) The single label for this issue.
        actions.append(
            Action(
                provider=PROVIDER,
                type="label",
                target=target,
                value=c.label,
                rationale=c.rationale or f"labelled {c.label}",
                evidence=c.evidence,
            )
        )
        # 2) Assignment — only if the model proposed a real collaborator.
        if c.assignee and (allowed is None or c.assignee in allowed):
            actions.append(
                Action(
                    provider=PROVIDER,
                    type="assign",
                    target=target,
                    value=c.assignee,
                    rationale=c.rationale or f"assigned to {c.assignee}",
                    evidence=c.evidence,
                )
            )
    return ProposalPayload(capability="triage", subject=subject, actions=actions)
