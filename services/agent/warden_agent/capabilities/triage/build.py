"""Turn triage classifications into a generic ``ProposalPayload``.

This is where the triage capability maps its internal reasoning onto the
platform's provider-agnostic ``Action`` shape. Every action it emits names the
``github_issues`` provider, which the runner knows how to execute.
"""
from __future__ import annotations

from warden_common.schemas import Action, ProposalPayload

from .types import IssueClassification

PROVIDER = "github_issues"


def build_payload(subject: str, classifications: list[IssueClassification]) -> ProposalPayload:
    actions: list[Action] = []
    for c in classifications:
        target = str(c.issue_number)
        # 1) Labels — severity + area + any extra suggested labels (deduped).
        labels: list[str] = []
        for lbl in (*c.suggested_labels, f"severity:{c.severity}", f"area:{c.area}"):
            if lbl and lbl not in labels:
                labels.append(lbl)
        for lbl in labels:
            actions.append(
                Action(
                    provider=PROVIDER,
                    type="label",
                    target=target,
                    value=lbl,
                    rationale=c.rationale or f"classified as {c.severity}/{c.area}",
                    evidence=c.evidence,
                )
            )
        # 2) Assignment — only if the model proposed one.
        if c.suggested_assignee:
            actions.append(
                Action(
                    provider=PROVIDER,
                    type="assign",
                    target=target,
                    value=c.suggested_assignee,
                    rationale=f"area {c.area} -> {c.suggested_assignee}",
                    evidence=c.evidence,
                )
            )
        # 3) Close as duplicate — only the higher-numbered (newer) issue.
        if c.duplicate_of and c.duplicate_of < c.issue_number:
            actions.append(
                Action(
                    provider=PROVIDER,
                    type="close",
                    target=target,
                    value=str(c.duplicate_of),
                    rationale=f"duplicate of #{c.duplicate_of}",
                    evidence=c.evidence,
                )
            )
    return ProposalPayload(capability="triage", subject=subject, actions=actions)
